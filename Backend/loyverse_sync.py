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
        
        print(f"📦 DEBUG LOYVERSE - Tipo de alerta recibida: {tipo}")
        # 🚨 ESCÁNER ABSOLUTO: Imprime TODO el código crudo que manda Loyverse
        print(f"🚨 PAQUETE COMPLETO: {evento}")
        
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
            data_obj = evento.get("data", {})
            
            # ⚡ FIX MEGA BLINDADO: Extraemos el pantalón sin importar cómo venga empacado
            lista_items = []
            if isinstance(data_obj, list):
                lista_items = data_obj
            elif isinstance(data_obj, dict):
                if "items" in data_obj:
                    lista_items = data_obj["items"]
                elif "item" in data_obj:
                    lista_items = [data_obj["item"]]
                else:
                    # Si Loyverse lo manda completamente suelto y sin llave
                    lista_items = [data_obj]
                
            print(f"🔍 DEBUG LOYVERSE - Pantalones encontrados en el paquete: {len(lista_items)}")
            
            for item_data in lista_items:
                nombre = item_data.get("item_name", "Sin Nombre")
                variantes = item_data.get("variants", [])
                
                if variantes:
                    sku = variantes[0].get("sku")
                    precio_crudo = variantes[0].get("price", 0.0)
                    precio = float(precio_crudo) if precio_crudo is not None else 0.0
                    
                    print(f"🔍 DEBUG LOYVERSE - Leyendo Pantalón: Nombre='{nombre}', SKU='{sku}', Precio={precio}")
                    
                    if sku:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku).first()
                        
                        if not pantalon_db:
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
                            pantalon_db.nombre = nombre
                            pantalon_db.precio = precio
                            print(f"🔄 Modelo actualizado desde Loyverse: {sku}")
                        
                        db.commit()
                    else:
                        print(f"⚠️ ERROR LOYVERSE: El pantalón '{nombre}' NO tiene SKU (REF) escrito en Loyverse, ignorado.")
                else:
                    print(f"⚠️ ERROR LOYVERSE: El pantalón '{nombre}' viene sin variantes/precio.")