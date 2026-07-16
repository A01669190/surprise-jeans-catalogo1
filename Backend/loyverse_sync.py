import urllib.request
import json
import models

# Tu token maestro de conexión
TOKEN_LOYVERSE = "b3dca41541684d0cb5dbcfeac1155736"

def descontar_stock_loyverse(sku, stock_after):
    """ Función que actualiza el inventario absoluto en la tablet """
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
    """ Función que escucha cuando crean un pantalón en la app o cobran en caja """
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
            # ⚡ EL FIX: Cambiamos "item" por "items" y lo leemos como lista
            lista_items = evento.get("data", {}).get("items", [])
            
            for item_data in lista_items:
                nombre = item_data.get("item_name", "Sin Nombre")
                variantes = item_data.get("variants", [])
                
                if variantes:
                    sku = variantes[0].get("sku")
                    precio = float(variantes[0].get("price", 0.0))
                    
                    if sku:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku).first()
                        
                        if not pantalon_db:
                            # Si es nuevo, lo creamos en la categoría "Nuevos"
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

async def procesar_webhooks_loyverse(eventos, db, manager):
    """ Función que escucha cuando crean un pantalón en la app o cobran en caja """
    for evento in eventos:
        tipo = evento.get("type")
        
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

        elif tipo in ["items.create", "items.update"]:
            # ⚡ FIX FINAL: Loyverse no usa la carpeta "data" aquí, los tira en la raíz.
            lista_items = evento.get("items", [])
            
            for item_data in lista_items:
                # Extraemos el nombre exacto que vimos en tus Rayos X
                nombre = item_data.get("item_name", "Sin Nombre")
                variantes = item_data.get("variants", [])
                
                if variantes:
                    sku = variantes[0].get("sku")
                    # ⚡ FIX FINAL 2: Loyverse le llama 'default_price', no 'price'
                    precio_crudo = variantes[0].get("default_price", 0.0)
                    precio = float(precio_crudo) if precio_crudo is not None else 0.0
                    
                    if sku:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku).first()
                        
                        if not pantalon_db:
                            cat = db.query(models.Categoria).filter(models.Categoria.nombre == "Nuevos").first()
                            if not cat:
                                cat = models.Categoria(nombre="Nuevos")
                                db.add(cat)
                                db.commit()
                                db.refresh(cat)
                            
                            # ⚡ FIX IMÁGENES: Intentamos jalar la foto de Loyverse
                            imagen_loyverse = item_data.get("image_url")
                            if not imagen_loyverse:
                                imagen_loyverse = "https://dummyimage.com/400x500/e0e7ff/3730a3&text=FOTO+PENDIENTE"
                                
                            nuevo = models.Pantalon(
                                codigo=sku, nombre=nombre, precio=precio, stock=0, categoria_id=cat.id,
                                imagen_url=imagen_loyverse # Asignamos la foto que nos mandó la tablet
                            )
                            db.add(nuevo)
                            print(f"🌟 Nuevo modelo sincronizado desde Loyverse: {sku} - {nombre}")
                        else:
                            pantalon_db.nombre = nombre
                            pantalon_db.precio = precio
                            print(f"🔄 Modelo actualizado desde Loyverse: {sku} - {nombre}")
                        
                        db.commit()
                    else:
                        print(f"⚠️ ERROR: El pantalón '{nombre}' NO tiene SKU (REF) escrito en Loyverse.")
                else:
                    print(f"⚠️ ERROR: El pantalón '{nombre}' viene sin variantes.")


def crear_articulo_loyverse(nombre, sku, precio):
    """ Envía un pantalón recién creado en la web directamente a la tablet de Loyverse """
    try:
        payload = json.dumps({
            "item_name": nombre,
            "variants": [
                {
                    "sku": sku,
                    "default_pricing_type": "FIXED",
                    "default_price": float(precio)
                }
            ]
        }).encode("utf-8")
        
        req = urllib.request.Request("https://api.loyverse.com/v1.0/items", data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req.add_header("Content-Type", "application/json")
        
        urllib.request.urlopen(req)
        print(f"✅ Sincronización Inversa: El modelo {sku} ({nombre}) se inyectó a Loyverse con éxito.")
        
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al empujar a Loyverse: {error_msg}")