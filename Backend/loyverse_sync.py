import json
import os
import asyncio
import datetime
import httpx  # ⚡ NUEVO: Motor asíncrono de alto rendimiento
import models

TOKEN_LOYVERSE = os.getenv("LOYVERSE_TOKEN", "")

async def obtener_catalogo_completo(token):
    """ Descarga TODOS los artículos de Loyverse de forma asíncrona y paginada """
    todos_los_items = []
    url = "https://api.loyverse.com/v1.0/items?limit=250"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        while url:
            try:
                respuesta = await client.get(url, headers=headers)
                respuesta.raise_for_status()
                datos = respuesta.json()
                
                todos_los_items.extend(datos.get("items", []))
                
                cursor = datos.get("cursor")
                if cursor:
                    url = f"https://api.loyverse.com/v1.0/items?limit=250&cursor={cursor}"
                    # ⚡ Pausa asíncrona anti-bloqueo sin congelar hilos
                    await asyncio.sleep(0.3) 
                else:
                    url = None
                    
            except Exception as e:
                print(f"❌ Error descargando catálogo paginado asíncrono: {e}")
                break
                
    return todos_los_items

async def descontar_stock_loyverse(sku, stock_after):
    """ Actualiza el inventario absoluto en la tablet de forma asíncrona """
    try:
        headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}", "Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            res_tienda = await client.get("https://api.loyverse.com/v1.0/stores", headers=headers)
            res_tienda.raise_for_status()
            store_id = res_tienda.json()["stores"][0]["id"]
            
            # ⚡ Motor de paginación infinita asíncrono
            items = await obtener_catalogo_completo(TOKEN_LOYVERSE)
            
            if not items:
                print(f"⚠️ El catálogo está vacío en Loyverse.")
                return
                
            variant_id = None
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
            
            ajuste_payload = {
                "inventory_levels": [{"store_id": store_id, "variant_id": variant_id, "stock_after": stock_after}]
            }
            
            res_ajuste = await client.post("https://api.loyverse.com/v1.0/inventory", json=ajuste_payload, headers=headers)
            res_ajuste.raise_for_status()
            print(f"✅ Loyverse actualizado (Async): Talla {sku} ahora tiene {stock_after} piezas.")
            
    except Exception as e:
        error_msg = e.response.text if hasattr(e, 'response') else str(e)
        print(f"❌ Error de Loyverse al actualizar stock: {error_msg}")

async def procesar_webhooks_loyverse(eventos, db, manager):
    """ Escucha ÚNICAMENTE cuando cobran en caja para restar el stock """
    for evento in eventos:
        tipo = evento.get("type")
        
        if tipo == "receipts.update":
            # ⚡ FIX: Evitar bucle infinito de doble descuento
            receipt_number = evento.get("data", {}).get("receipt", {}).get("receipt_number", "")
            if str(receipt_number).startswith("WEB-"):
                print(f"🔄 Ignorando recibo {receipt_number} porque ya fue descontado por la web.")
                continue
                
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

async def crear_articulo_loyverse(nombre, sku, precio, nombre_categoria="General", color="Original"):
    """ Crea artículos de forma asíncrona con tolerancia a fallos """
    headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res_cat = await client.get("https://api.loyverse.com/v1.0/categories", headers=headers)
            res_cat.raise_for_status()
            categorias = res_cat.json().get("categories", [])
            
            cat_id = None
            for c in categorias:
                if c["name"].lower() == nombre_categoria.lower():
                    cat_id = c["id"]
                    break
                    
            if not cat_id:
                payload_cat = {"name": nombre_categoria}
                res_nueva_cat = await client.post("https://api.loyverse.com/v1.0/categories", json=payload_cat, headers=headers)
                res_nueva_cat.raise_for_status()
                cat_id = res_nueva_cat.json()["id"]

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
            
            res_item = await client.post("https://api.loyverse.com/v1.0/items", json=payload_dict, headers=headers)
            res_item.raise_for_status()
            print(f"✅ OMNICANAL (Async): {sku} ({color}) creado en Loyverse con sus 7 tallas.")
        except Exception as e:
            error_msg = e.response.text if hasattr(e, 'response') else str(e)
            print(f"❌ Error al crear en Loyverse: {error_msg}")

async def crear_cliente_loyverse(nombre, correo, telefono):
    """ Sincroniza clientes de forma asíncrona """
    try:
        datos_cliente = {"name": nombre, "email": correo}
        if telefono:
            datos_cliente["phone_number"] = telefono
            
        headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}", "Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post("https://api.loyverse.com/v1.0/customers", json=datos_cliente, headers=headers)
            res.raise_for_status()
            print(f"👤 Cliente guardado en Loyverse (Async): {nombre}")
    except Exception as e:
        error_msg = e.response.text if hasattr(e, 'response') else str(e)
        print(f"❌ Error al crear cliente en Loyverse: {error_msg}")

async def eliminar_articulo_loyverse(sku_hijo_exacto):
    """ Destruye un artículo de la tablet de forma asíncrona """
    try:
        items = await obtener_catalogo_completo(TOKEN_LOYVERSE)
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
            
        headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res_del = await client.delete(f"https://api.loyverse.com/v1.0/items/{item_id}", headers=headers)
            res_del.raise_for_status()
            print(f"✅ OMNICANAL (Async): Artículo con variante {sku_hijo_exacto} eliminado de Loyverse.")
        
    except Exception as e:
        error_msg = e.response.text if hasattr(e, 'response') else str(e)
        print(f"❌ Error al eliminar en Loyverse: {error_msg}")

async def actualizar_categoria_loyverse(sku_hijo_exacto, nombre_categoria):
    """ Actualiza la categoría en tiempo real de forma asíncrona """
    try:
        headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res_cat = await client.get("https://api.loyverse.com/v1.0/categories", headers=headers)
            res_cat.raise_for_status()
            categorias = res_cat.json().get("categories", [])
            
            cat_id = None
            for c in categorias:
                if c["name"].lower() == nombre_categoria.lower():
                    cat_id = c["id"]
                    break
                    
            if not cat_id:
                payload_cat = {"name": nombre_categoria}
                res_nueva_cat = await client.post("https://api.loyverse.com/v1.0/categories", json=payload_cat, headers=headers)
                res_nueva_cat.raise_for_status()
                cat_id = res_nueva_cat.json()["id"]

            items = await obtener_catalogo_completo(TOKEN_LOYVERSE)
            
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
            
            res_upd = await client.post("https://api.loyverse.com/v1.0/items", json=item_a_modificar, headers=headers)
            res_upd.raise_for_status()
            print(f"✅ OMNICANAL (Async): Categoría actualizada en Loyverse para el SKU {sku_hijo_exacto}.")
        
    except Exception as e:
        error_msg = e.response.text if hasattr(e, 'response') else str(e)
        print(f"❌ Error al actualizar categoría en Loyverse: {error_msg}")

async def generar_recibo_virtual(correo_cliente, folio_interno, items_comprados, total_pagado):
    """ Genera el recibo digital en la tablet de forma asíncrona """
    try:
        headers = {"Authorization": f"Bearer {TOKEN_LOYVERSE}", "Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            res_tienda = await client.get("https://api.loyverse.com/v1.0/stores", headers=headers)
            store_id = res_tienda.json()["stores"][0]["id"]

            res_emp = await client.get("https://api.loyverse.com/v1.0/employees", headers=headers)
            employee_id = res_emp.json()["employees"][0]["id"]

            res_pos = await client.get("https://api.loyverse.com/v1.0/pos_devices", headers=headers)
            pos_id = res_pos.json()["pos_devices"][0]["id"]

            res_pay = await client.get("https://api.loyverse.com/v1.0/payment_types", headers=headers)
            payment_type_id = res_pay.json()["payment_types"][0]["id"]
            
            customer_id = None
            if correo_cliente:
                res_cust = await client.get(f"https://api.loyverse.com/v1.0/customers?email={correo_cliente}", headers=headers)
                clientes = res_cust.json().get("customers", [])
                if clientes:
                    customer_id = clientes[0]["id"]

            catalogo = await obtener_catalogo_completo(TOKEN_LOYVERSE)

            line_items = []
            for item in items_comprados:
                sku_buscado = item["sku"]
                for cat_item in catalogo:
                    for var in cat_item.get("variants", []):
                        if var.get("sku") == sku_buscado:
                            line_items.append({
                                "item_id": cat_item["id"],
                                "variant_id": var["variant_id"],
                                "quantity": item["cantidad"],
                                "price": item["precio"],
                                "gross_total_money": item["precio"] * item["cantidad"],
                                "total_money": item["precio"] * item["cantidad"]
                            })
                            break

            if not line_items:
                print("⚠️ Loyverse: No se armó el recibo porque no se encontraron las tallas.")
                return

            fecha_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

            recibo = {
                "receipt_number": f"WEB-{folio_interno:04d}",
                "receipt_type": "SALE",
                "store_id": store_id,
                "pos_id": pos_id,
                "employee_id": employee_id,
                "receipt_date": fecha_iso,
                "total_money": total_pagado,
                "net_amount": total_pagado,
                "line_items": line_items,
                "payments": [{"payment_type_id": payment_type_id, "money_amount": total_pagado}]
            }

            if customer_id:
                recibo["customer_id"] = customer_id

            res_receipt = await client.post("https://api.loyverse.com/v1.0/receipts", json=recibo, headers=headers)
            res_receipt.raise_for_status()
            
        print(f"🧾✅ Recibo WEB-{folio_interno:04d} tecleado virtualmente de forma asíncrona.")

    except Exception as e:
        error_msg = e.response.text if hasattr(e, 'response') else str(e)
        print(f"❌ Error al generar recibo en Loyverse: {error_msg}")