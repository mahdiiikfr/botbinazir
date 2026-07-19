import openstack
import config
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio

# OpenStack connection needs to be run in a thread pool as the SDK is synchronous
executor = ThreadPoolExecutor(max_workers=5)

def _get_connection():
    return openstack.connect(
        auth_url=config.OS_AUTH_URL,
        project_name=config.OS_PROJECT_NAME,
        username=config.OS_USERNAME,
        password=config.OS_PASSWORD,
        project_domain_name=config.OS_PROJECT_DOMAIN_NAME,
        user_domain_name=config.OS_USER_DOMAIN_NAME,
    )

def _list_flavors():
    try:
        conn = _get_connection()
        flavors = list(conn.compute.flavors())
        return [{"id": f.id, "name": f.name, "ram": f.ram, "vcpus": f.vcpus, "disk": f.disk} for f in flavors]
    except Exception as e:
        logging.error(f"Error listing flavors: {e}")
        return []

def _list_images():
    try:
        conn = _get_connection()
        images = list(conn.compute.images())
        return [{"id": i.id, "name": i.name} for i in images]
    except Exception as e:
        logging.error(f"Error listing images: {e}")
        return []

def _create_server(name, image_id, flavor_id, network_id):
    try:
        conn = _get_connection()
        # Find network
        network = conn.network.find_network(network_id)

        server = conn.compute.create_server(
            name=name,
            image_id=image_id,
            flavor_id=flavor_id,
            networks=[{"uuid": network.id}] if network else None
        )
        server = conn.compute.wait_for_server(server)
        return {"id": server.id, "status": server.status, "admin_pass": server.admin_password}
    except Exception as e:
        logging.error(f"Error creating server: {e}")
        return None

def _delete_server(server_id):
    try:
        conn = _get_connection()
        conn.compute.delete_server(server_id)
        return True
    except Exception as e:
        logging.error(f"Error deleting server: {e}")
        return False

def _reboot_server(server_id):
    try:
        conn = _get_connection()
        conn.compute.reboot_server(server_id, "HARD")
        return True
    except Exception as e:
        logging.error(f"Error rebooting server: {e}")
        return False

def _rebuild_server(server_id, image_id, password):
    try:
        conn = _get_connection()
        conn.compute.rebuild_server(server_id, image=image_id, admin_password=password)
        return True
    except Exception as e:
        logging.error(f"Error rebuilding server: {e}")
        return False

def _change_server_password(server_id, new_password):
    try:
        conn = _get_connection()
        conn.compute.change_server_password(server_id, new_password)
        return True
    except Exception as e:
        logging.error(f"Error changing server password: {e}")
        return False

def _get_server_status(server_id):
    try:
        conn = _get_connection()
        server = conn.compute.get_server(server_id)
        return server.status if server else None
    except Exception as e:
        logging.error(f"Error getting server status: {e}")
        return None

async def list_flavors():
    return await asyncio.get_event_loop().run_in_executor(executor, _list_flavors)

async def list_images():
    return await asyncio.get_event_loop().run_in_executor(executor, _list_images)

async def create_server(name, image_id, flavor_id, network_id):
    return await asyncio.get_event_loop().run_in_executor(executor, _create_server, name, image_id, flavor_id, network_id)

async def delete_server(server_id):
    return await asyncio.get_event_loop().run_in_executor(executor, _delete_server, server_id)

async def reboot_server(server_id):
    return await asyncio.get_event_loop().run_in_executor(executor, _reboot_server, server_id)

async def get_server_status(server_id):
    return await asyncio.get_event_loop().run_in_executor(executor, _get_server_status, server_id)

async def rebuild_server(server_id, image_id, password):
    return await asyncio.get_event_loop().run_in_executor(executor, _rebuild_server, server_id, image_id, password)

async def change_server_password(server_id, new_password):
    return await asyncio.get_event_loop().run_in_executor(executor, _change_server_password, server_id, new_password)
