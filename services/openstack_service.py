import openstack
import logging
import asyncio
import config

# Hardcoded Flavor Base Prices in USD per hour (calculated from monthly price / 720 hours)
# These represent the exact raw cost from HostVDS
FLAVOR_PRICES_USD = {
    "hostvds-1": 0.001375,     # $0.99/mo
    "hostvds-2": 0.002764,     # $1.99/mo
    "hostvds-4": 0.005542,     # $3.99/mo
    "hostvds-8": 0.011097,     # $7.99/mo
    "hostvds-8-2": 0.013875,   # $9.99/mo
    "hostvds-16": 0.022208,    # $15.99/mo
    "highload-1": 0.004153,    # $2.99/mo
    "highload-2": 0.008319,    # $5.99/mo
    "highload-4": 0.016653,    # $11.99/mo
    "highload-8": 0.033319,    # $23.99/mo
    "highload-16": 0.066653,   # $47.99/mo
    "highload-24": 0.099986,   # $71.99/mo
}

DEFAULT_HOURLY_USD = 0.001375  # fallback if flavor not matched

def get_connection():
    return openstack.connect(
        auth_url=config.OS_AUTH_URL,
        project_id=config.OS_PROJECT_ID,
        project_name=config.OS_PROJECT_NAME,
        username=config.OS_USERNAME,
        password=config.OS_PASSWORD,
        user_domain_name="Default",
        project_domain_name="Default",
        region_name=config.OS_REGION_NAME,
    )

async def list_flavors() -> list:
    """List flavors with details and mapped base price"""
    def _run():
        conn = get_connection()
        flavors = []
        for flavor in conn.compute.flavors():
            # Get base price or default
            price_usd = FLAVOR_PRICES_USD.get(flavor.name, DEFAULT_HOURLY_USD)
            flavors.append({
                "id": flavor.id,
                "name": flavor.name,
                "ram": flavor.ram,
                "disk": flavor.disk,
                "vcpus": flavor.vcpus,
                "price_usd_hourly": price_usd,
            })
        # Sort by price
        flavors.sort(key=lambda x: x["price_usd_hourly"])
        return flavors
    return await asyncio.to_thread(_run)

async def list_images() -> list:
    """List available active images, skipping OLD ones unless requested"""
    def _run():
        conn = get_connection()
        images = []
        for img in conn.compute.images(status="active"):
            if "old_" in img.name.lower():
                continue
            images.append({
                "id": img.id,
                "name": img.name,
                "status": img.status,
            })
        images.sort(key=lambda x: x["name"])
        return images
    return await asyncio.to_thread(_run)

async def list_networks() -> list:
    """List available networks"""
    def _run():
        conn = get_connection()
        networks = []
        for net in conn.network.networks():
            networks.append({
                "id": net.id,
                "name": net.name,
            })
        networks.sort(key=lambda x: x["name"])
        return networks
    return await asyncio.to_thread(_run)

async def create_server(name: str, flavor_id: str, image_id: str, network_id: str, root_password: str) -> dict:
    """Create a new virtual server"""
    def _run():
        conn = get_connection()
        # Create server params
        server = conn.compute.create_server(
            name=name,
            flavor_id=flavor_id,
            image_id=image_id,
            networks=[{"uuid": network_id}],
            admin_pass=root_password,
        )
        return {
            "id": server.id,
            "name": server.name,
            "status": server.status,
            "admin_pass": root_password,
        }
    return await asyncio.to_thread(_run)

async def delete_server(server_id: str) -> bool:
    """Delete completely a server"""
    def _run():
        conn = get_connection()
        conn.compute.delete_server(server_id)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error deleting server {server_id}: {e}")
        return False

async def get_server_status(server_id: str) -> dict:
    """Get server status and ip address"""
    def _run():
        conn = get_connection()
        server = conn.compute.get_server(server_id)
        if not server:
            return None

        # Parse IP Address from addresses dict
        ip_addr = "N/A"
        addresses = server.addresses
        if addresses:
            for net_name, net_ips in addresses.items():
                for ip_info in net_ips:
                    if ip_info.get("version") == 4:
                        ip_addr = ip_info.get("addr")
                        break
                if ip_addr != "N/A":
                    break

        return {
            "id": server.id,
            "name": server.name,
            "status": server.status,  # ACTIVE, SHUTOFF, REBUILD, ERROR, etc.
            "ip_address": ip_addr,
        }
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error checking status for server {server_id}: {e}")
        return None

async def start_server(server_id: str) -> bool:
    def _run():
        conn = get_connection()
        conn.compute.start_server(server_id)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error starting server {server_id}: {e}")
        return False

async def stop_server(server_id: str) -> bool:
    def _run():
        conn = get_connection()
        conn.compute.stop_server(server_id)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error stopping server {server_id}: {e}")
        return False

async def reboot_server(server_id: str, hard: bool = False) -> bool:
    def _run():
        conn = get_connection()
        reboot_type = "HARD" if hard else "SOFT"
        conn.compute.reboot_server(server_id, reboot_type)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error rebooting server {server_id}: {e}")
        return False

async def rebuild_server(server_id: str, image_id: str, admin_pass: str) -> bool:
    def _run():
        conn = get_connection()
        conn.compute.rebuild_server(server_id, image_id=image_id, admin_pass=admin_pass)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error rebuilding server {server_id}: {e}")
        return False

async def change_server_password(server_id: str, admin_pass: str) -> bool:
    """Change server password (attempts to change online, if unsupported, user will be advised to rebuild)"""
    def _run():
        conn = get_connection()
        conn.compute.change_server_password(server_id, admin_pass)
        return True
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logging.error(f"Error changing server password online: {e}")
        return False
