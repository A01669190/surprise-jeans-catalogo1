import urllib.request
import json
import os
import models

# Cargar token desde variables de entorno por seguridad
TOKEN_LOYVERSE = os.getenv("LOYVERSE_TOKEN", "")

def descontar_stock_loyverse(sku, stock_after):
    """ Actualiza el inventario absoluto en la tablet para una variante ESPECÍFICA """
    try:
        req_tienda = urllib.request.Request("https://api.loyverse.com/v1.0/stores")
        req_tienda.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        store_id = json.loads(urllib.request.urlopen(req_tienda).read().decode('utf-8'))["stores"][0]["id"]
        
        # ⚡ EL FIX: Pedimos 250 artículos de golpe (el máximo) para no dejar pantalones fuera
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items?limit=250")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        items = json.loads(urllib.request.urlopen(req_item).read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ El catálogo está vacío en Loyverse.")
            return
            
        variant_id = None
        # ⚡ EL GRAN FIX: Quitamos el [0] destructivo. Ahora busca en TODOS los artículos.
        for item in items:
            for variante in item.get("variants", []):
                if variante.get("sku") == sku:
                    variant_id = variante["variant_id"]
                    break
            if variant_id:
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
        
        if tipo == "receipts.update":
            line_items = evento.get("data", {}).get("receipt", {}).get("line_items", [])
            for item in line_items:
                sku_variante = item.get("sku")
                cantidad = int(item.get("quantity", 1))
                
                if sku_variante:
                    variante = db.query(models.VarianteTalla).filter(models.VarianteTalla.sku == sku_variante).first()
                    if variante and variante.stock >= cantidad:
                        variante.stock -= cantidad
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
                    
                    variante_db = db.query(models.VarianteTalla).filter(models.VarianteTalla.sku == sku_crudo).first()
                    
                    if variante_db:
                        pantalon_db = variante_db.pantalon
                        pantalon_db.nombre = nombre
                        pantalon_db.precio = precio
                        db.commit()
                        print(f"🔄 Modelo sincronizado con Loyverse: {pantalon_db.codigo}")
                    else:
                        sku_padre = sku_crudo.rsplit('-', 2)[0] if sku_crudo.count('-') >= 2 else sku_crudo.split('-')[0]
                        
                        if sku_padre:
                            pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.codigo == sku_padre).first()
                            if not pantalon_db:
                                cat = db.query(models.Categoria).filter(models.Categoria.nombre == "Nuevos").first()
                                if not cat:
                                    cat = models.Categoria(nombre="Nuevos")
                                    db.add(cat)
                                    db.commit()
                                    db.refresh(cat)
                                    
                                nuevo = models.Pantalon(
                                    codigo=sku_padre, nombre=nombre, precio=precio, stock=0, categoria_id=cat.id,
                                    imagen_url="https://dummyimage.com/400x500/e0e7ff/3730a3&text=FOTO+PENDIENTE"
                                )
                                db.add(nuevo)
                                db.commit()
                                print(f"🌟 Nuevo modelo descargado desde Loyverse: {sku_padre}")

def crear_articulo_loyverse(nombre, sku, precio, nombre_categoria="General", color="Original"):
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

        color_sku = color.replace(" ", "").upper()

        payload_dict = {
            "item_name": nombre,
            "category_id": cat_id,
            "track_stock": True,
            "option1_name": "Talla",
            "option2_name": "Color",
            "variants": [
                {"sku": f"{sku}-{color_sku}-3", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "3", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-5", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "5", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-7", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "7", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-9", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "9", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-11", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "11", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-13", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "13", "option2_value": color},
                {"sku": f"{sku}-{color_sku}-15", "default_pricing_type": "FIXED", "default_price": precio, "option1_value": "15", "option2_value": color}
            ]
        }
        
        payload_final = json.dumps(payload_dict).encode("utf-8")
        
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items", data=payload_final, method="POST")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req_item.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_item)
        print(f"✅ OMNICANAL: {sku} ({color}) creado en Loyverse con sus 7 tallas.")
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

def eliminar_articulo_loyverse(sku_hijo_exacto):
    """ Busca un artículo por el SKU EXACTO de una de sus tallas y lo destruye de la tablet """
    try:
        # ⚡ EL FIX: Pedimos hasta 250 artículos
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items?limit=250")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        res_item = urllib.request.urlopen(req_item)
        items = json.loads(res_item.read().decode('utf-8')).get("items", [])
        
        if not items:
            return
            
        item_id = None
        for item in items:
            for variante in item.get("variants", []):
                if variante.get("sku") == sku_hijo_exacto:
                    item_id = item["id"]
                    break
            if item_id:
                break
                
        if not item_id:
            print(f"⚠️ Loyverse: El código '{sku_hijo_exacto}' no se encontró con precisión.")
            return
            
        req_del = urllib.request.Request(f"https://api.loyverse.com/v1.0/items/{item_id}", method="DELETE")
        req_del.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        urllib.request.urlopen(req_del)
        print(f"✅ OMNICANAL: Artículo con variante {sku_hijo_exacto} eliminado de Loyverse con éxito.")
        
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al eliminar en Loyverse: {error_msg}")

def actualizar_categoria_loyverse(sku_hijo_exacto, nombre_categoria):
    """ Busca un artículo en Loyverse y le actualiza su categoría en tiempo real """
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

        # ⚡ EL FIX: Pedimos hasta 250 artículos
        req_item = urllib.request.Request("https://api.loyverse.com/v1.0/items?limit=250")
        req_item.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        res_item = urllib.request.urlopen(req_item)
        items = json.loads(res_item.read().decode('utf-8')).get("items", [])
        
        item_a_modificar = None
        for item in items:
            for variante in item.get("variants", []):
                if variante.get("sku") == sku_hijo_exacto:
                    item_a_modificar = item
                    break
            if item_a_modificar:
                break
                
        if not item_a_modificar:
            return

        item_a_modificar["category_id"] = cat_id
        
        payload_update = json.dumps(item_a_modificar).encode("utf-8")

        req_upd = urllib.request.Request("https://api.loyverse.com/v1.0/items", data=payload_update, method="POST")
        req_upd.add_header("Authorization", f"Bearer {TOKEN_LOYVERSE}")
        req_upd.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req_upd)
        print(f"✅ OMNICANAL: Categoría actualizada en Loyverse para el SKU {sku_hijo_exacto}.")
        
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error al actualizar categoría en Loyverse: {error_msg}")