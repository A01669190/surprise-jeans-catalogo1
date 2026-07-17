import requests
import os

# Tu Token de Skydropx (Lo ideal es ponerlo en las variables de entorno de Render)
SKYDROPX_API_KEY = os.getenv("SKYDROPX_API_KEY", "wwJSo7mpIOXEi5ZzTTSDd-RWU7lddvHg2_4xPvgmKwk")
URL_SKYDROPX = "https://api.skydropx.com/v1/shipments"

def generar_guia_envio(pedido_id: int, nombre_cliente: str, direccion: dict, peso_kg: float = 1.0):
    """
    Se comunica con Skydropx para generar una guía real automáticamente.
    """
    headers = {
        "Authorization": f"Token token={SKYDROPX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 1. Armamos el paquete de datos con la dirección de tu tienda y la del cliente
    payload = {
        "address_from": {
            "province": "Jalisco", 
            "city": "Guadalajara", 
            "name": "SURPRISE JEANS by YSK", 
            "zip": "44100",
            "address1": "Calle de la Tienda 123", 
            "phone": "3312345678", 
            "email": "contacto@surprisejeans.com"
        },
        "address_to": {
            "province": direccion.get("estado", "Jalisco"),
            "city": direccion.get("ciudad", "Guadalajara"),
            "name": nombre_cliente,
            "zip": direccion.get("codigo_postal", "00000"),
            "address1": direccion.get("calle_y_numero", "Conocido"),
            "phone": direccion.get("telefono", "0000000000"),
            "email": direccion.get("email", "cliente@correo.com")
        },
        "parcels": [{
            "weight": peso_kg,
            "distance_unit": "CM", "mass_unit": "KG",
            "length": 30, "height": 10, "width": 20
        }]
    }

    try:
        # 2. Creamos el embarque en Skydropx
        respuesta = requests.post(URL_SKYDROPX, headers=headers, json=payload)
        datos = respuesta.json()
        
        if respuesta.status_code != 200:
            print(f"❌ Error Skydropx al crear embarque: {datos}")
            return None

        # 3. Extraemos el ID del embarque y buscamos la tarifa más barata
        embarque_id = datos["data"]["id"]
        rates = datos.get("included", [])
        
        if not rates:
            print(f"⚠️ No se encontraron paqueterías disponibles para el CP {direccion.get('codigo_postal')}")
            return None
            
        rate_barato_id = rates[0]["id"] 
        
        # 4. Solicitamos la generación del PDF y el código de rastreo
        url_label = "https://api.skydropx.com/v1/labels"
        payload_label = {"rate_id": rate_barato_id, "label_format": "pdf"}
        res_label = requests.post(url_label, headers=headers, json=payload_label)
        
        data_label = res_label.json()
        
        # Retornamos el diccionario con los datos mágicos
        return {
            "tracking_number": data_label["data"]["attributes"]["tracking_number"],
            "tracking_url": data_label["data"]["attributes"]["tracking_url_provider"],
            "label_pdf": data_label["data"]["attributes"]["label_url"]
        }
        
    except Exception as e:
        print(f"❌ Error crítico de conexión con paquetería: {e}")
        return None