import urllib.request
import json
import models

TOKEN_LOYVERSE = "b3dca41541684d0cb5dbcfeac1155736"

def descontar_stock_loyverse(sku, stock_after):
    """ Función que actualiza el inventario absoluto en la tablet para una variante ESPECÍFICA """
    try:
        req_tienda = urllib.request.Request("https://api.loyverse.com/v1.0/stores")
        req_tienda.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        store_id = json.loads(urllib.request.urlopen(req_tienda).read().decode('utf-8'))["stores"][0]["id"]
        
        # Le pedimos a Loyverse el artículo
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        items = json.loads(urllib.request.urlopen(req_item).read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ El código {sku} no existe en Loyverse.")
            return
            
        # ⚡ EL GRAN FIX: Loyverse devuelve el artículo con TODAS sus tallas.
        # Tenemos que buscar cuál de esas tallas es la que coincide con nuestro SKU exacto.
        variant_id = None
        for variante in items[0]["variants"]:
            if variante["sku"] == sku:
                variant_id = variante["variant_id"]
                break
                
        if not variant_id:
            print(f"⚠️ La talla específica {sku} no se encontró en el artículo de Loyverse.")
            return
        
        ajuste_payload = json.dumps({
            "inventory_levels": [{"store_id": store_id, "variant_id": variant_id, "stock_after": stock_after}]
        }).encode("utf-8")
        
        req_ajuste = urllib.request.Request("https://api.loyverse.com/v1.0/inventory", data=ajuste_payload, method="POST")
        req_ajuste.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req_ajuste.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_ajuste)
        print(f"✅ Loyverse actualizado: Talla {sku} ahora tiene {stock_after} piezas.")
        
    except Exception as e:
        print(f"❌ Error de Loyverse al actualizar stock: {e}")

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
        # 3. SI ELIMINAN UN PANTALÓN DESDE LA TABLET FÍSICA
        elif tipo == "items.delete":
            lista_items = evento.get("items", [])
            for item_data in lista_items:
                # Cuando Loyverse elimina, nos manda su ID. Buscamos variantes asociadas en la web.
                # Nota: Es más seguro manejar el borrado maestro desde la Web, pero aquí capturamos la señal
                print(f"🗑️ Alerta de eliminación recibida desde Loyverse para el ID: {item_data.get('id')}")

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


def crear_articulo_loyverse(nombre, sku, precio, nombre_categoria="General"):
    import urllib.request
    import json
    import os
    
    token = os.getenv("LOYVERSE_TOKEN", "")
    if not token: return
    
    try:
        # 1. 🔍 BUSCAR O CREAR CATEGORÍA EN LOYVERSE
        req_cat = urllib.request.Request("https://api.loyverse.com/v1.0/categories")
        req_cat.add_header("Authorization", f"Bearer {token}")
        res_cat = urllib.request.urlopen(req_cat)
        categorias = json.loads(res_cat.read().decode('utf-8')).get("categories", [])
        
        cat_id = None
        for c in categorias:
            if c["name"].lower() == nombre_categoria.lower():
                cat_id = c["id"]
                break
                
        if not cat_id:
            # Si no existe en la tablet, la creamos
            payload_cat = json.dumps({"name": nombre_categoria}).encode("utf-8")
            req_nueva_cat = urllib.request.Request("https://api.loyverse.com/v1.0/categories", data=payload_cat, method="POST")
            req_nueva_cat.add_header("Authorization", f"Bearer {token}")
            req_nueva_cat.add_header("Content-Type", "application/json")
            res_nueva_cat = urllib.request.urlopen(req_nueva_cat)
            cat_id = json.loads(res_nueva_cat.read().decode('utf-8'))["id"]

        # 2. 📦 CREAR EL PANTALÓN ASIGNÁNDOLE LA CATEGORÍA
        # 2. 📦 CREAR EL PANTALÓN ASIGNÁNDOLE LA CATEGORÍA
        payload_dict = {
            "item": {
                "item_name": nombre,
                "category_id": cat_id,
                "option1_name": "Talla",
                "variants": [
                    {"sku": f"{sku}-3", "pricing_type": "FIXED", "default_price": precio, "option1_value": "3"},
                    {"sku": f"{sku}-5", "pricing_type": "FIXED", "default_price": precio, "option1_value": "5"},
                    {"sku": f"{sku}-7", "pricing_type": "FIXED", "default_price": precio, "option1_value": "7"},
                    {"sku": f"{sku}-9", "pricing_type": "FIXED", "default_price": precio, "option1_value": "9"},
                    {"sku": f"{sku}-11", "pricing_type": "FIXED", "default_price": precio, "option1_value": "11"},
                    {"sku": f"{sku}-13", "pricing_type": "FIXED", "default_price": precio, "option1_value": "13"},
                    {"sku": f"{sku}-15", "pricing_type": "FIXED", "default_price": precio, "option1_value": "15"}
                ]
            }
        }
        # Empaquetamos correctamente usando json.dumps()
        payload_final = json.dumps(payload_dict).encode("utf-8")
        
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items", data=payload_final, method="POST")
        req_item.add_header("Authorization", f"Bearer {token}")
        req_item.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_item)
        
        print(f"✅ OMNICANAL: Modelo {sku} creado en Loyverse bajo la categoría '{nombre_categoria}'.")
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al crear en Loyverse: {error_msg}")

def crear_cliente_loyverse(nombre, correo, telefono):
    """ Sincroniza a un cliente recién registrado en la web con la tablet física """
    try:
        payload = json.dumps({
            "name": nombre,
            "email": correo,
            "phone_number": telefono if telefono else ""
        }).encode("utf-8")
        
        req = urllib.request.Request("https://api.loyverse.com/v1.0/customers", data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req)
        print(f"👤 Sincronización de Cliente: {nombre} fue guardado en Loyverse.")
    except Exception as e:
        print(f"❌ Error al crear cliente en Loyverse: {e}")

def eliminar_articulo_loyverse(sku):
    """ Busca un artículo por su SKU en Loyverse y lo destruye para mantener limpio el catálogo """
    try:
        # 1. Buscamos el ID interno de Loyverse usando el SKU
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        items = json.loads(urllib.request.urlopen(req_item).read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ No se encontró el SKU {sku} en Loyverse para eliminar.")
            return
            
        item_id = items[0]["id"]
        
        # 2. Mandamos la orden de eliminación definitiva
        req_delete = urllib.request.Request(f"https://api.loyverse.com/v1.0/items/{item_id}", method="DELETE")
        req_delete.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        urllib.request.urlopen(req_delete)
        print(f"🗑️ Sincronización de Eliminación: Modelo {sku} borrado de Loyverse.")
    except Exception as e:
        print(f"❌ Error al eliminar artículo en Loyverse: {e}")

def eliminar_articulo_loyverse(sku):
    import urllib.request
    import json
    import os
    
    token = os.getenv("LOYVERSE_TOKEN", "")
    if not token: return
    
    try:
        # 1. Buscamos el pantalón en Loyverse por su SKU para robar su ID secreto
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {token}")
        res_item = urllib.request.urlopen(req_item)
        items = json.loads(res_item.read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ Loyverse: El código {sku} ya no existía en la tablet.")
            return
            
        item_id = items[0]["id"]
        
        # 2. Mandamos la orden (DELETE) directamente a ese ID
        req_del = urllib.request.Request(f"https://api.loyverse.com/v1.0/items/{item_id}", method="DELETE")
        req_del.add_header("Authorization", f"Bearer {token}")
        urllib.request.urlopen(req_del)
        
        print(f"🗑️ OMNICANAL: El modelo {sku} fue destruido de Loyverse con éxito.")
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al eliminar en Loyverse: {error_msg}")