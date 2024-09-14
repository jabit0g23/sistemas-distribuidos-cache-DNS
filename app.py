from flask import Flask, request, jsonify
from rediscluster import RedisCluster
import os
import grpc
from dns_pb2_grpc import DNSServiceStub
from dns_pb2 import DNSRequest

# Inicialización de la aplicación Flask
app = Flask(__name__)

def get_redis_nodes():
    # Obtiene los nodos de Redis desde la variable de entorno 'REDIS_NODES'
    nodes = os.getenv('REDIS_NODES', '').split(',')
    return [{"host": node.split(':')[0], "port": int(node.split(':')[1])} for node in nodes if node]

# Configuración de los nodos Redis usando la función anterior
startup_nodes = get_redis_nodes()

# Verificar si los nodos están configurados correctamente
if not startup_nodes:
    raise ValueError("No Redis nodes configured. Please check the REDIS_NODES environment variable.")

# Conectar al cluster de Redis usando los nodos configurados
try:
    redis_client = RedisCluster(startup_nodes=startup_nodes, decode_responses=True)
    print("Connected to Redis cluster successfully.")
except Exception as e:
    print(f"Error connecting to Redis cluster: {e}")
    raise

def query_dns_via_grpc(domain):
    # Conectar al servidor gRPC
    channel = grpc.insecure_channel('grpc-server:50051')  # Asegúrate de que este host y puerto sean correctos
    stub = DNSServiceStub(channel)
    try:
        # Llama al método GetDNS en el servidor gRPC
        response = stub.GetDNS(DNSRequest(domain=domain))
        # Convierte el resultado a una lista directamente
        return list(response.ips)
    except grpc.RpcError as e:
        print(f"gRPC Error: {e}")
        return ["Error fetching DNS record"]

@app.route('/dns', methods=['GET'])
def get_dns_record():
    domain = request.args.get('domain')
    if not domain:
        return jsonify({"error": "Domain parameter is missing"}), 400

    try:
        # Intenta obtener el registro desde el caché Redis
        result = redis_client.get(domain)
        if result:
            return jsonify({"domain": domain, "record": result, "source": "cache"}), 200

        # Si no está en caché, realiza una consulta DNS a través del servidor gRPC
        print(f"Record not found in cache for {domain}, querying gRPC server...")
        result = query_dns_via_grpc(domain)  # Llamada al gRPC server

        # Guarda en Redis el resultado serializado
        redis_client.set(domain, ', '.join(result))
        return jsonify({"domain": domain, "record": result, "source": "gRPC"}), 200

    except Exception as e:
        print(f"Error fetching DNS record for {domain}: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "API is running"}), 200

if __name__ == "__main__":
    # Iniciar la API Flask en el puerto 5001
    app.run(host="0.0.0.0", port=5001)
