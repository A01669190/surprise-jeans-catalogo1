import urllib.request
import json
import models

# Tu token maestro de conexión
TOKEN_LOYVERSE = "b3dca41541684d0cb5dbcfeac1155736"

def descontar_stock_loyverse(sku, stock_after):
    try:
        req_tienda = urllib.request.Request("https://api.loyverse.com/v1.0/stores")
        req_tienda.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        store_id = json.loads(urllib.request.urlopen(req_tienda).read().decode('utf-8'))["stores"][0]["id"]
        
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        items = json.loads(urllib.request.urlopen(req_item).read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ El código {sku} no existe en Loyverse.")
            return
            
        variant_id = items[0]["variants"][0]["variant_id"]
        
        ajuste_payload = json.dumps({
            "inventory_levels": [{"store_id": store_id, "variant_id": variant_id, "stock_after": stock_after}]
        }).encode("utf-8")
        
        req_ajuste = urllib.request.Request("https://api.loyverse.com/v1.0/inventory", data=ajuste_payload, method="POST")
        req_ajuste.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req_ajuste.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_ajuste)
        print(f"✅ Loyverse actualizado: Modelo {sku} a {stock_after} piezas.")
        
    except Exception as e:
        print(f"❌ Error de Loyverse: {e}")

async def procesar_webhooks_loyverse(eventos, db, manager):
    """ Este es el nuevo cerebro que decide qué hacer con la información que llega de la tienda """
    for evento in eventos:
        tipo = evento.get("type")
        
        # 1. SI SE HACE UNA VENTA EN LA CAJA REGISTRADORA FÍSICA
        if tipo == "receipts.update":
            line_items = evento.get("data", {}).get("receipt", {}).get("line_items", [])
            for item in line_items:
                sku = item.get("sku")
                cantidad = int(item.get("quantity", 1))
                if sku:
                    pantalon = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku).first()
                    if pantalon and pantalon.stock >= cantidad:
                        pantalon.stock -= cantidad
                        db.commit()
                        await manager.broadcast("NUEVO_PEDIDO")
                        print(f"✅ Venta física: Se restaron {cantidad} de {sku}")

        # 2. 🚀 OPCIÓN 2: SI CREAN O EDITAN UN PANTALÓN EN LOYVERSE (CATÁLOGO AUTOMÁTICO)
        elif tipo in ["items.create", "items.update"]:
            item_data = evento.get("data", {}).get("item", {})
            nombre = item_data.get("item_name", "Sin Nombre")
            variantes = item_data.get("variants", [])
            
            if variantes:
                sku = variantes[0].get("sku")
                precio = float(variantes[0].get("price", 0.0))
                
                if sku:
                    pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku).first()
                    
                    if not pantalon_db:
                        # Si es nuevo, lo creamos en una categoría provisional
                        cat = db.query(models.Categoria).filter(models.Categoria.nombre == "Nuevos").first()
                        if not cat:
                            cat = models.Categoria(nombre="Nuevos")
                            db.add(cat)
                            db.commit()
                            db.refresh(cat)
                            
                        nuevo = models.Pantalon(
                            codigo=sku, nombre=nombre, precio=precio, stock=0, categoria_id=cat.id,
                            imagen_url="https://dummyimage.com/400x500/e0e7ff/3730a3&text=FOTO+PENDIENTE"
                        )
                        db.add(nuevo)
                        print(f"🌟 Nuevo modelo sincronizado desde Loyverse: {sku}")
                    else:
                        # Si ya existía, solo actualizamos el precio y nombre
                        pantalon_db.nombre = nombre
                        pantalon_db.precio = precio
                        print(f"🔄 Modelo actualizado desde Loyverse: {sku}")
                    
                    db.commit()