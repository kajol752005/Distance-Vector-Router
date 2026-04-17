import socket
import json
import threading
import time
import os

BIND_IP = "0.0.0.0"
MY_IP = os.getenv("MY_IP", "127.0.0.1")
NEIGHBORS = [n for n in os.getenv("NEIGHBORS", "").split(",") if n]
PORT = 5000
INFINITY = 16  

routing_table = {}

def get_local_subnet(ip):
    """Simple helper to derive the /24 subnet from an IP."""
    parts = ip.split('.')
    if len(parts) < 3: return "127.0.0.0/24"
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

local_subnet = get_local_subnet(MY_IP)
routing_table[local_subnet] = [0, "0.0.0.0"]

router_lock = threading.Lock()

def broadcast_updates():
    """Periodically sends the routing table to all known neighbors."""
    while True:
        time.sleep(5)
       
        with router_lock:
            for neighbor in NEIGHBORS:
                packet = {
                    "router_id": MY_IP,
                    "version": 1.0,
                    "routes": []
                }
               
                for subnet, info in routing_table.items():
                    distance, next_hop = info
                   
                    if next_hop == neighbor:
                        continue
                       
                    packet["routes"].append({
                        "subnet": subnet,
                        "distance": distance
                    })

                try:
                    print(f"[SEND] Sending table to neighbor {neighbor}...")
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        s.sendto(json.dumps(packet).encode(), (neighbor, PORT))
                except Exception as e:
                    print(f"[ERROR] Could not send to {neighbor}: {e}")

def update_logic(neighbor_ip, routes_from_neighbor):
    """Implements Bellman-Ford algorithm and updates the Linux routing table."""
    with router_lock:
        changed = False
        for route in routes_from_neighbor:
            subnet = route["subnet"]
            advertised_dist = route["distance"]
            new_dist = advertised_dist + 1
           
            if (subnet not in routing_table) or \
               (new_dist < routing_table[subnet][0]) or \
               (neighbor_ip == routing_table[subnet][1]):
               
                if subnet in routing_table and routing_table[subnet][0] == new_dist:
                    continue

                routing_table[subnet] = [new_dist, neighbor_ip]
                changed = True
               
                if new_dist > 0 and new_dist < INFINITY:
                    print(f"[TABLE UPDATE] Route to {subnet} via {neighbor_ip} cost {new_dist}")
                    
                    os.system(f"ip route replace {subnet} via {neighbor_ip}")
                elif new_dist >= INFINITY:
                    print(f"[INFINITY] Route to {subnet} is unreachable.")

def listen_for_updates():
    """Listens for incoming UDP packets on PORT 5000."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((BIND_IP, PORT))
        print(f"--- Router {MY_IP} Initialized ---")
        print(f"Local Subnet: {local_subnet}")
        print(f"Neighbors: {NEIGHBORS}")
        print(f"Listening on port {PORT}...")
       
        while True:
            data, addr = s.recvfrom(4096)
            neighbor_ip = addr[0]
            print(f"[RECEIVE] Packet received from {neighbor_ip}")
           
            try:
                packet = json.loads(data.decode())
                update_logic(neighbor_ip, packet["routes"])
            except Exception as e:
                print(f"[ERROR] Failed to process packet from {neighbor_ip}: {e}")

if __name__ == "__main__":
    os.system("echo 1 > /proc/sys/net/ipv4/ip_forward")
   
    sender_thread = threading.Thread(target=broadcast_updates, daemon=True)
    sender_thread.start()
    listen_for_updates()