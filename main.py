import subprocess
import requests
import json
import networkx as nx
import matplotlib.pyplot as plt
import os
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
                "Name": container['Names'][0].lstrip('/'),  # Nombre del contenedor
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
        G.add_node(node_name, label="Nodo")

        for vm in nodo["Attributes"]:
            vm_name = vm["Name"]
            G.add_node(vm_name, label="VM")
            G.add_edge(node_name, vm_name)

            for stack in vm["Attributes"]:
                stack_name = stack["Name"]
                G.add_node(stack_name, label="Stack")
                G.add_edge(vm_name, stack_name)

                for container in stack["Attributes"]:
                    container_name = "c_"+container["Name"]
                    G.add_node(container_name, label="Contenedor")
                    G.add_edge(stack_name, container_name)
        
        # Dibujar el grafo
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(G)
        labels = {node: node for node in G.nodes()}
        nx.draw(G, pos, with_labels=True, labels=labels, node_size=2000, node_color="lightblue", edge_color="gray", font_size=10)
        plt.show()
        
def build_graph(data, graph=None, parent=None):
    if graph is None:
        graph = nx.DiGraph()
    
    if isinstance(data, list):
        for item in data:
            build_graph(item, graph)
    elif isinstance(data, dict):
        node_name = data.get("Name", "Unknown")
        attributes = data.get("Attributes", [])
        attr_text = ", ".join([f"{k}: {v}" for attr in attributes for k, v in attr.items() if isinstance(attr, dict)])
        graph.add_node(node_name, label=node_name, title=attr_text)
        
        if parent:
            graph.add_edge(parent, node_name)
        
        for attr in attributes:
            if isinstance(attr, dict) and "Name" in attr:
                build_graph(attr, graph, node_name)
    
    return graph

def visualize_json(json_data):
    graph = build_graph(json_data)
    net = Network(notebook=True, directed=True)
    
    for node, data in graph.nodes(data=True):
        net.add_node(node, label=data.get("label", node), title=data.get("title", ""))
    
    for source, target in graph.edges():
        net.add_edge(source, target)
    
    net.show("graph.html")

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
        
        visualize_json(stacks)
        print("El grafo ha sido guardado como 'graph.html'. Ábrelo en tu navegador.")

    except requests.exceptions.RequestException as e:
        print(f"Error al comunicarse con la API de Portainer: {e}")
    except KeyError as e:
        print(f"Error al procesar la respuesta de la API: {e}")

if __name__ == "__main__":
    main()
