import subprocess
import requests
import json
import networkx as nx
import matplotlib.pyplot as plt
import os
import ast
from dotenv import load_dotenv
from pyvis.network import Network

load_dotenv()

# Configuración: Cambia estas variables según tu entorno de Portainer
PORTAINER_URL = os.getenv("url")
API_KEY = os.getenv("key")

def guardar_json(nombre_archivo, datos):
    """Guarda los datos en un archivo JSON."""
    with open(nombre_archivo, 'w') as archivo:
        json.dump(datos, archivo, indent=4)

def obtener_stacks():

    comando = f"http --verify=no --form GET https://192.168.0.62:9443/api/stacks X-API-Key:{API_KEY}"

    try:
        resultado = subprocess.check_output(comando, shell=True, stderr=subprocess.STDOUT, text=True)
        json_object = json.loads(resultado)
        return json_object

    except subprocess.CalledProcessError as e:
        # Captura errores de ejecución
        print(f"Error al ejecutar el comando: {e}")
        print("Salida de error:")
        print(e)

def obtener_contenedores():
    
    comando = f"http --verify=no --form GET https://192.168.0.62:9443/api/endpoints/2/docker/containers/json X-API-Key:{API_KEY}"

    try:
        resultado = subprocess.check_output(comando, shell=True, stderr=subprocess.STDOUT, text=True)
        json_object = json.loads(resultado)
        return json_object

    except subprocess.CalledProcessError as e:
        # Captura errores de ejecución
        print(f"Error al ejecutar el comando: {e}")
        print("Salida de error:")
        print(e)

def generate_stacks_with_containers(containers_file, stacks_file, output_file):
    # Cargar los archivos JSON con los contenedores y los stacks
    with open(containers_file) as f:
        containers = json.load(f)

    with open(stacks_file) as f:
        stacks = json.load(f)

    # Crear un diccionario para mapear los StackId con los nombres de los stacks
    stack_map = {stack['Id']: stack['Name'] for stack in stacks}

    # Crear el resultado
    node_stacks = []

    for stack_id, stack_name in stack_map.items():
        
        # Filtrar los contenedores que pertenecen a este stack (usando Labels)
        stack_containers = [
            {
            "Name": f"c_{container['Names'][0].lstrip('/')}" if container['Names'][0].lstrip('/') == stack_name else container['Names'][0].lstrip('/'),  # Nombre del contenedor
            "Attributes": [
                {
                "IP": port.get('IP', 'N/A'),
                "PrivatePort": port.get('PrivatePort'),
                "PublicPort": port.get('PublicPort'),
                "Type": port.get('Type')
                }
                for port in container.get('Ports', [])
            ]
            }
            for container in containers
            if container.get('Labels', {}).get('com.docker.compose.project') == stack_name
        ]

        # Agregar la información del stack al resultado
        node_stacks.append({
            "Name": stack_name,
            "Attributes": stack_containers
        })
        
    result = [{"Name": "N100", "Attributes":[{"Name":"LXC_0","Attributes": node_stacks}]}]

    # Guardar el resultado en un archivo JSON
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=4)

    print(f"El archivo '{output_file}' ha sido generado correctamente.")

def generate_and_draw_graf(filename):
    # Cargar el archivo JSON
    with open(filename, 'r') as f:
        data = json.load(f)

    G = nx.Graph()
    
    for nodo in data:
        node_name = nodo["Name"]
        G.add_node(node_name, label="Nodo", color="red")

        for vm in nodo["Attributes"]:
            vm_name = vm["Name"]
            G.add_node(vm_name, label="VM", color="blue")
            G.add_edge(node_name, vm_name)

            for stack in vm["Attributes"]:
                stack_name = stack["Name"]
                G.add_node(stack_name, label="Stack", color="green")
                G.add_edge(vm_name, stack_name)

                for container in stack["Attributes"]:
                    container_name = "c_"+container["Name"]
                    G.add_node(container_name, label="Contenedor", color="yellow")
                    G.add_edge(stack_name, container_name)
        
        # Dibujar el grafo
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(G)
        labels = {node: node for node in G.nodes()}
        colors = [G.nodes[node]['color'] for node in G.nodes()]
        nx.draw(G, pos, with_labels=True, labels=labels, node_size=2000, node_color=colors, edge_color="gray", font_size=10)
        plt.show()

def visualize_json(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
        
    net = Network(notebook=True, directed=True)
    
    def add_nodes_edges(data, parent=None):
        if isinstance(data, list):
            for item in data:
                add_nodes_edges(item, parent)
        elif isinstance(data, dict):
            node_name = data.get("Name", "Unknown")
            attributes = data.get("Attributes", [])
            attr_text = ", ".join([f"{k}: {v}" for attr in attributes for k, v in attr.items() if isinstance(attr, dict)])
            
            color = "red" if parent is None else "blue" if "N100" in parent else "green" if "LXC" in parent else "yellow"
            net.add_node(node_name, label=node_name, title=attr_text, color=color)
            
            if parent:
                net.add_edge(parent, node_name)
            
            for attr in attributes:
                if isinstance(attr, dict) and "Name" in attr:
                    add_nodes_edges(attr, node_name)
    
    add_nodes_edges(data)
    
    net.show("graph.html")

    print("El grafo ha sido guardado como 'graph.html'. Ábrelo en tu navegador.")

def get_ports(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    
    ret = ""
    
    for nodo in data:
        for vm in nodo["Attributes"]:
            for stack in vm["Attributes"]:
                for container in stack["Attributes"]:
                    ports = [(attr['PrivatePort'], attr['PublicPort']) for attr in container["Attributes"] if 'PrivatePort' in attr and 'PublicPort' in attr]
                    # print(f"Contenedor: {container['Name']}, Pares de puertos: {ports}")
                    if ports != []:
                        ret += f"{container['Name']}: {ports}\n"

    with open('ports.txt', 'w') as f:
        f.write(ret)

def generate_dashy(filename, ip_address="192.168.0.62"):
    with open(filename, "r") as f:
        lines = f.readlines()
    
    servicios = {}
    for line in lines:
        if line.strip():
            nombre, puertos = line.split(": ")
            puertos = ast.literal_eval(puertos.strip())
            servicios[nombre] = puertos
    
    items = []
    for servicio, puertos in servicios.items():
        if puertos:
            puerto = puertos[0][1]  # Primer puerto de la lista
            if puerto is not None:
                items.append({
                    "title": f"{servicio}",
                    "url": f"http://{ip_address}:{puerto}",
                    "icon": "",
                    "id" : f"{servicio}"
                })
    
    with open("dashy.txt", "w") as f:
        for item in items:
            f.write(f"      - title: {item['title']}\n")
            f.write(f"        url: {item['url']}\n")
            f.write(f"        icon: {item['icon']}\n")
            f.write(f"        id: {item['id']}\n\n")
    
    return items

def main():
    try:
        # Paso 1: Obtener la lista de stacks
        print("Obteniendo la lista de stacks...")
        stacks = obtener_stacks()

        if not stacks:
            print("No se encontraron stacks en Portainer.")
            return
        else:
            guardar_json("stacks.json", stacks)

        # Paso 2: Obtener la lista de contenedores
        print("Obteniendo la lista de contenedores...")
        containers = obtener_contenedores()
        
        if not containers:
            print("No se encontraron contenedores en Portainer.")
            return
        else:
            guardar_json("containers.json", containers)
        
        generate_stacks_with_containers('containers.json', 'stacks.json', 'stacks_with_containers.json')

        # generate_and_draw_graf('stacks_with_containers.json')
        
        visualize_json('stacks_with_containers.json')

        get_ports('stacks_with_containers.json')
    except requests.exceptions.RequestException as e:
        print(f"Error al comunicarse con la API de Portainer: {e}")
    except KeyError as e:
        print(f"Error al procesar la respuesta de la API: {e}")

    print(generate_dashy('ports.txt'))

if __name__ == "__main__":
    main()