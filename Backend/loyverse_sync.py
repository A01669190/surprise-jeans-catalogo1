import urllib.request
import json
import os
import models

# Cargar token desde variables de entorno por seguridad
TOKEN_LOYVERSE = os.getenv("LOYVERSE_TOKEN", "b3dca41541684d0cb5dbcfeac1155736")

def descontar_stock_loyverse(sku, stock_after):
    """ Actualiza el inventario absoluto en la tablet para una variante ESPECÍFICA """
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
            
        variant_id = None
        for variante in items[0]["variants"]:
            if variante["sku"] == sku:
                variant_id = variante["variant_id"]
                break
                
        if not variant_id:
            print(f"⚠️ La talla específica {sku} no se encontró en Loyverse.")
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
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error de Loyverse al actualizar stock: {error_msg}")

async def procesar_webhooks_loyverse(eventos, db, manager):
    """ Escucha ÚNICAMENTE cuando cobran en caja para restar el stock """
    for evento in eventos:
        tipo = evento.get("type")
        
        # 1. SI SE HACE UNA VENTA EN LA CAJA REGISTRADORA FÍSICA
        if tipo == "receipts.update":
            line_items = evento.get("data", {}).get("receipt", {}).get("line_items", [])
            for item in line_items:
                sku_variante = item.get("sku")
                cantidad = int(item.get("quantity", 1))
                
                if sku_variante:
                    variante = db.query(models.VarianteTalla).filter(models.VarianteTalla.sku == sku_variante).first()
                    if variante and variante.stock >= cantidad:
                        # Restamos a la talla
                        variante.stock -= cantidad
                        # Restamos al total del pantalón papá
                        if variante.pantalon and variante.pantalon.stock >= cantidad:
                            variante.pantalon.stock -= cantidad
                        
                        db.commit()
                        await manager.broadcast("NUEVO_PEDIDO")
                        print(f"✅ Venta física: Se restaron {cantidad} de la talla {sku_variante}")

        elif tipo in ["items.create", "items.update"]:
            lista_items = evento.get("items", [])
            
            for item_data in lista_items:
                nombre = item_data.get("item_name", "Sin Nombre")
                variantes = item_data.get("variants", [])
                
                if variantes:
                    sku_crudo = variantes[0].get("sku", "")
                    precio_crudo = variantes[0].get("default_price", 0.0)
                    precio = float(precio_crudo) if precio_crudo is not None else 0.0
                    
                    # ⚡ ESCUDO ANTI-CLONES
                    sku_padre = sku_crudo.split('-')[0] if sku_crudo and '-' in sku_crudo else sku_crudo
                    
                    if sku_padre:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku_padre).first()
                        
                        if not pantalon_db:
                            cat = db.query(models.Categoria).filter(models.Categoria.nombre == "Nuevos").first()
                            if not cat:
                                cat = models.Categoria(nombre="Nuevos")
                                db.add(cat)
                                db.commit()
                                db.refresh(cat)
                                
                            imagen_loyverse = item_data.get("image_url")
                            if not imagen_loyverse:
                                imagen_loyverse = "https://dummyimage.com/400x500/e0e7ff/3730a3&text=FOTO+PENDIENTE"
                                
                            nuevo = models.Pantalon(
                                codigo=sku_padre, nombre=nombre, precio=precio, stock=0, categoria_id=cat.id,
                                imagen_url=imagen_loyverse 
                            )
                            db.add(nuevo)
                            print(f"🌟 Nuevo modelo sincronizado desde Loyverse: {sku_padre} - {nombre}")
                        else:
                            pantalon_db.nombre = nombre
                            pantalon_db.precio = precio
                            print(f"🔄 Modelo actualizado desde Loyverse: {sku_padre} - {nombre}")
                        
                        db.commit()
                    else:
                        print(f"⚠️ ERROR: El artículo '{nombre}' NO tiene SKU.")

        elif tipo == "items.delete":
             lista_items = evento.get("items", [])
             for item_data in lista_items:
                 print(f"🗑️ Alerta: Artículo eliminado desde Loyverse con ID: {item_data.get('id')}")

def crear_articulo_loyverse(nombre, sku, precio, nombre_categoria="General"):
    try:
        req_cat = urllib.request.Request("https://api.loyverse.com/v1.0/categories")
        req_cat.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        res_cat = urllib.request.urlopen(req_cat)
        categorias = json.loads(res_cat.read().decode('utf-8')).get("categories", [])
        
        cat_id = None
        for c in categorias:
            if c["name"].lower() == nombre_categoria.lower():
                cat_id = c["id"]
                break
                
        if not cat_id:
            payload_cat = json.dumps({"name": nombre_categoria}).encode("utf-8")
            req_nueva_cat = urllib.request.Request("https://api.loyverse.com/v1.0/categories", data=payload_cat, method="POST")
            req_nueva_cat.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
            req_nueva_cat.add_header("Content-Type", "application/json")
            res_nueva_cat = urllib.request.urlopen(req_nueva_cat)
            cat_id = json.loads(res_nueva_cat.read().decode('utf-8'))["id"]

        payload_dict = {
            "item_name": nombre,
            "category_id": cat_id,
            "track_stock": True,
            "option1_name": "Talla",
            "variants": [
                {"sku": f"{sku}-3", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "3"},
                {"sku": f"{sku}-5", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "5"},
                {"sku": f"{sku}-7", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "7"},
                {"sku": f"{sku}-9", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "9"},
                {"sku": f"{sku}-11", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "11"},
                {"sku": f"{sku}-13", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "13"},
                {"sku": f"{sku}-15", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "15"}
            ]
        }
        
        payload_final = json.dumps(payload_dict).encode("utf-8")
        
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items", data=payload_final, method="POST")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req_item.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_item)
        print(f"✅ OMNICANAL: {sku} creado en Loyverse con sus 7 tallas.")
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al crear en Loyverse: {error_msg}")

def crear_cliente_loyverse(nombre, correo, telefono):
    """ Sincroniza a un cliente recién registrado con la tablet física """
    try:
        payload = json.dumps({"name": nombre, "email": correo, "phone_number": telefono if telefono else ""}).encode("utf-8")
        req = urllib.request.Request("https://api.loyverse.com/v1.0/customers", data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req)
        print(f"👤 Cliente guardado en Loyverse: {nombre}")
    except Exception as e:
        print(f"❌ Error al crear cliente en Loyverse: {e}")

def eliminar_articulo_loyverse(sku):
    """ Busca un artículo por su SKU y lo destruye de la tablet (con precisión láser) """
    try:
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        res_item = urllib.request.urlopen(req_item)
        items = json.loads(res_item.read().decode('utf-8')).get("items", [])
        
        if not items:
            return
            
        # ⚡ ESCUDO DE PRECISIÓN: Verificamos que sea el modelo EXACTO buscando su primera talla
        item_id = None
        sku_esperado = f"{sku}-3"  # Ejemplo: Si intentas borrar SJ-210, debe existir un SJ-210-3
        
        for item in items:
            for variante in item.get("variants", []):
                if variante.get("sku") == sku_esperado:
                    item_id = item["id"]
                    break
            if item_id:
                break
                
        if not item_id:
            print(f"⚠️ Loyverse: El código '{sku}' es un fantasma o no es exacto. Se omite para proteger otros modelos.")
            return
            
        # Si pasó el escudo, entonces sí es el verdadero y lo destruimos
        req_del = urllib.request.Request(f"https://api.loyverse.com/v1.0/items/{item_id}", method="DELETE")
        req_del.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        urllib.request.urlopen(req_del)
        
    except Exception as e:
        pass