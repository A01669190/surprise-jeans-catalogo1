import requests
import os
import logging

# Configuración de logs
logger = logging.getLogger("SurpriseJeans")

def generar_guia_envio(pedido_id: int, nombre_cliente: str, direccion: dict, peso_kg: float = 1.0):
    API_KEY = os.getenv("SKYDROPX_API_KEY", "")
    URL_SKYDROPX = "https://api-demo.skydropx.com/v1/shipments"
    
    headers = {
        "Authorization": f"Token token={API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "address_from": {
            "province": "Jalisco", "city": "Guadalajara", 
            "name": "SURPRISE JEANS by YSK", "zip": "44100",
            "address1": "Calle de la Tienda 123", "phone": "3312345678", 
            "email": "contacto@surprisejeans.com"
        },
        "address_to": {
            "province": direccion.get("estado", "Jalisco"),
            "city": direccion.get("ciudad", "Guadalajara"),
            "name": nombre_cliente,
            "zip": direccion.get("codigo_postal") or "44100",
            "address1": direccion.get("calle_y_numero") or "Conocido",
            "phone": direccion.get("telefono") or "3300000000",
            "email": direccion.get("email") or "cliente@correo.com"
        },
        "parcels": [{"weight": peso_kg, "distance_unit": "CM", "mass_unit": "KG", "length": 30, "height": 10, "width": 20}]
    }

    try:
        respuesta = requests.post(URL_SKYDROPX, headers=headers, json=payload)
        datos = respuesta.json()
        
        if respuesta.status_code != 200:
            logger.error(f"Error Skydropx [Pedido {pedido_id}]: {datos}")
            return None

        embarque_id = datos["data"]["id"]
        rates = datos.get("included", [])
        if not rates: return None
            
        rate_barato_id = rates[0]["id"] 
        
        # Generar Etiqueta
        res_label = requests.post("https://api-demo.skydropx.com/v1/labels", 
                                  headers=headers, 
                                  json={"rate_id": rate_barato_id, "label_format": "pdf"})
        
        data_label = res_label.json()
        return {
            "tracking_number": data_label["data"]["attributes"]["tracking_number"],
            "tracking_url": data_label["data"]["attributes"]["tracking_url_provider"],
            "label_pdf": data_label["data"]["attributes"]["label_url"]
        }
    except Exception as e:
        logger.error(f"Error crítico en logística: {e}")
        return None