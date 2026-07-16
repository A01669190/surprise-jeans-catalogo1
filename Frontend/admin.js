// ==========================================
// 1. CONFIGURACIÓN
// ==========================================
const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

// ==========================================
// 2. SISTEMA DE LOGIN (JWT)
// ==========================================
async function verificarAcceso() {
    const inputPassword = document.getElementById('input-password').value;
    const formData = new URLSearchParams();
    formData.append('username', 'admin');
    formData.append('password', inputPassword);

    try {
        const respuesta = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        if (respuesta.ok) {
            const data = await respuesta.json();
            sessionStorage.setItem('token_vip', data.access_token); 
            const panel = document.getElementById('panel-login');
            panel.style.opacity = '0';
            setTimeout(() => { panel.style.display = 'none'; }, 500);
        } else {
            document.getElementById('error-password').classList.remove('hidden');
            document.getElementById('input-password').value = ''; 
        }
    } catch (error) { 
        console.error("Error de conexión en el login:", error); 
        alert("No se pudo conectar con el servidor.");
    }
}

function obtenerTokenHeader() {
    return { 'Authorization': `Bearer ${sessionStorage.getItem('token_vip')}` };
}

// ==========================================
// 3. INICIALIZACIÓN
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
    cargarInventarioAdmin(); 
});

// ==========================================
// 4. GESTIÓN DE CATEGORÍAS
// ==========================================
async function cargarCategoriasEnSelect() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        if (!respuesta.ok) throw new Error("Fallo al obtener categorías");
        
        const categorias = await respuesta.json();
        
        const select = document.getElementById('categoria');
        const selectEdit = document.getElementById('edit-categoria'); 
        const listaAdmin = document.getElementById('lista-categorias-admin'); 
        
        // Limpiamos los contenedores
        if(select) select.innerHTML = ''; 
        if(selectEdit) selectEdit.innerHTML = '';
        if(listaAdmin) listaAdmin.innerHTML = ''; 

        categorias.forEach(cat => {
            // Llenar Select 1
            if(select) { 
                const opcion = document.createElement('option');
                opcion.value = cat.id; 
                opcion.textContent = cat.nombre;
                select.appendChild(opcion); 
            }
            // Llenar Select de Edición
            if(selectEdit) { 
                const opcionEdit = document.createElement('option');
                opcionEdit.value = cat.id; 
                opcionEdit.textContent = cat.nombre;
                selectEdit.appendChild(opcionEdit); 
            }
            // Llenar Etiquetas Visuales
            if(listaAdmin) {
                const li = document.createElement('li');
                li.className = 'bg-gray-50 text-gray-700 text-xs font-semibold px-3 py-1.5 rounded-full flex items-center gap-2 border border-gray-200 shadow-sm';
                li.innerHTML = `
                    ${cat.nombre} 
                    <button type="button" onclick="borrarCategoria(${cat.id})" class="text-rose-500 hover:text-white hover:bg-rose-500 rounded-full w-4 h-4 flex items-center justify-center transition-colors">×</button>
                `;
                listaAdmin.appendChild(li);
            }
        });
    } catch (error) { 
        console.error("Error al cargar categorías:", error); 
    }
}

document.getElementById('formulario-categoria').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('nombre', document.getElementById('nueva-categoria').value);
    
    try {
        const respuesta = await fetch(`${API_URL}/categorias`, { 
            method: 'POST', 
            headers: obtenerTokenHeader(), 
            body: formData 
        });
        
        if (respuesta.ok) { 
            alert('¡Categoría creada con éxito!'); 
            document.getElementById('nueva-categoria').value = ''; 
            cargarCategoriasEnSelect(); 
        } else {
            alert('La sesión ha caducado. Recarga la página.');
        }
    } catch (error) { 
        console.error("Error creando categoría:", error); 
    }
});

async function borrarCategoria(id) {
    if(!confirm("¿Estás seguro de borrar esta categoría?")) return;
    
    try {
        const respuesta = await fetch(`${API_URL}/categorias/${id}`, { 
            method: 'DELETE', 
            headers: obtenerTokenHeader() 
        });
        
        if (respuesta.ok) {
            cargarCategoriasEnSelect();
        } else { 
            const errorData = await respuesta.json(); 
            alert(`No se pudo borrar: ${errorData.detail}`); 
        }
    } catch (error) { 
        console.error("Error borrando categoría:", error); 
    }
}

// ==========================================
// 5. CARGA MASIVA (EXCEL / CSV)
// ==========================================
const formExcel = document.getElementById('formulario-excel');
if(formExcel) {
    formExcel.addEventListener('submit', async (e) => {
        e.preventDefault();
        const archivoInput = document.getElementById('archivo-excel');
        const archivo = archivoInput.files[0];
        const btnSubir = document.getElementById('btn-subir-excel');
        
        if (!archivo) return;
        
        btnSubir.innerText = 'Procesando archivo...'; 
        btnSubir.disabled = true;

        const formData = new FormData(); 
        formData.append('archivo', archivo);
        
        try {
            const respuesta = await fetch(`${API_URL}/pantalones/excel`, { 
                method: 'POST', 
                headers: obtenerTokenHeader(), 
                body: formData 
            });
            
            const data = await respuesta.json();
            
            if (respuesta.ok) { 
                alert(`¡Éxito! ${data.mensaje}`); 
                cargarCategoriasEnSelect(); 
                cargarInventarioAdmin(); 
            } else {
                alert(`Error en el archivo: ${data.error}`);
            }
        } catch (error) { 
            console.error("Error subiendo Excel:", error);
            alert("Error de conexión al subir el archivo."); 
        } finally { 
            btnSubir.innerText = 'PROCESAR'; 
            btnSubir.disabled = false; 
            archivoInput.value = ''; 
        }
    });
}

function descargarPlantilla() {
    const contenido = "Codigo,Nombre,Precio,Stock,Categoria,Foto_URL\nSJ-001,Skinny Azul,150,10,Skinny,https://ejemplo.com/foto1.jpg\nSJ-002,Mom Jeans Rotos,180,5,Mom,\nSJ-003,Cargo Negro,200,20,Cargo,";
    const blob = new Blob([contenido], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a"); 
    link.setAttribute("href", URL.createObjectURL(blob));
    link.setAttribute("download", "Plantilla_SurpriseJeans_V2.csv");
    document.body.appendChild(link); 
    link.click(); 
    document.body.removeChild(link);
}

// ==========================================
// 6. CARGA MANUAL EN COLA
// ==========================================
let pantalonesEnCola = [];

document.getElementById('formulario-admin').addEventListener('submit', (e) => {
    e.preventDefault();
    const codigo = document.getElementById('codigo').value;
    const nombre = document.getElementById('nombre').value;
    const precio = document.getElementById('precio').value;
    const stock = document.getElementById('stock').value;
    const catSelect = document.getElementById('categoria');
    const foto = document.getElementById('foto').files[0];
    
    if(!foto) return;

    pantalonesEnCola.push({ 
        codigo: codigo, 
        nombre: nombre, 
        precio: precio, 
        stock: stock, 
        categoria_id: catSelect.value, 
        foto: foto 
    });
    
    document.getElementById('formulario-admin').reset(); 
    document.getElementById('stock').value = 1;
    actualizarUICola(); 
});

function actualizarUICola() {
    const lista = document.getElementById('lista-cola');
    const btnSubir = document.getElementById('btn-subir-todos');
    
    lista.innerHTML = '';
    document.getElementById('contador-cola').innerText = pantalonesEnCola.length;
    
    if (pantalonesEnCola.length > 0) {
        btnSubir.classList.remove('hidden');
    } else {
        btnSubir.classList.add('hidden');
    }

    pantalonesEnCola.forEach((p, i) => {
        const li = document.createElement('li'); 
        li.className = 'py-3 flex justify-between items-center text-sm';
        li.innerHTML = `
            <div>
                <span class="font-black text-indigo-600">[${p.codigo}]</span> 
                <span class="font-bold">${p.nombre}</span> 
                <span class="text-gray-500">($${p.precio}) - Stock: ${p.stock}</span>
            </div>
            <button type="button" onclick="eliminarDeCola(${i})" class="text-rose-500 font-bold hover:bg-rose-100 rounded-full w-6 h-6 flex items-center justify-center pb-1">×</button>
        `;
        lista.appendChild(li);
    });
}

function eliminarDeCola(index) { 
    pantalonesEnCola.splice(index, 1); 
    actualizarUICola(); 
}

async function subirTodos() {
    const btn = document.getElementById('btn-subir-todos'); 
    btn.innerText = 'Subiendo al catálogo...'; 
    btn.disabled = true;
    
    let exitos = 0;
    
    // Leemos la cola de atrás hacia adelante para no perder los datos si fallan
    for (let i = pantalonesEnCola.length - 1; i >= 0; i--) {
        let p = pantalonesEnCola[i];
        const fd = new FormData();
        fd.append('codigo', p.codigo); 
        fd.append('nombre', p.nombre); 
        fd.append('precio', p.precio);
        fd.append('stock', p.stock); 
        fd.append('categoria_id', p.categoria_id); 
        fd.append('foto', p.foto);
        
        try { 
            const respuesta = await fetch(`${API_URL}/pantalones`, { 
                method: 'POST', 
                headers: obtenerTokenHeader(), 
                body: fd 
            });
            
            if (respuesta.ok) {
                exitos++;
                // Solo si la carga fue un éxito, lo borramos de la lista de espera
                pantalonesEnCola.splice(i, 1);
            } else {
                // Si el servidor lo rechaza, te lanza la alerta y NO lo borra de la lista
                alert(`❌ El servidor rechazó el modelo: ${p.nombre}. (Verifica que formateaste la BD).`);
            }
        } catch(e) {
            console.error("Fallo al subir:", p.nombre, e);
            alert(`⚠️ Error de red al intentar subir: ${p.nombre}. Revisa tu conexión.`);
        }
    }
    
    if(exitos > 0) {
        alert(`¡Se subieron ${exitos} modelos con éxito!`);
    }
    
    // Actualizamos visualmente la interfaz sin perder los que hayan fallado
    actualizarUICola(); 
    cargarInventarioAdmin(); 
    
    btn.innerText = '🚀 SUBIR TODOS AL CATÁLOGO'; 
    btn.disabled = false;
}

// ==========================================
// 7. INVENTARIO ACTUAL
// ==========================================
async function cargarInventarioAdmin() {
    try {
        const respuesta = await fetch(`${API_URL}/pantalones`);
        if (!respuesta.ok) throw new Error("Fallo al descargar los pantalones");
        
        const pantalones = await respuesta.json();
        const contenedor = document.getElementById('lista-inventario'); 
        
        contenedor.innerHTML = '';
        
        if(pantalones.length === 0) {
            contenedor.innerHTML = '<p class="text-sm text-gray-500 text-center py-4">El inventario está vacío.</p>';
            return;
        }

        pantalones.forEach(p => {
            const div = document.createElement('div'); 
            div.className = 'flex justify-between items-center p-3 bg-gray-50 rounded-lg border border-gray-200';
            
            // ESCUDO DE SEGURIDAD: Evita que nombres o códigos vacíos crasheen la app
            const nomSeguro = p.nombre ? String(p.nombre).replace(/'/g, "\\'") : 'Sin Nombre';
            const codSeguro = p.codigo ? String(p.codigo).replace(/'/g, "\\'") : 'S/C';
            
            div.innerHTML = `
                <div class="flex items-center gap-4">
                    <img src="${p.imagen_url}" class="w-12 h-12 object-cover rounded-md shadow-sm">
                    <div>
                        <p class="font-bold text-sm text-gray-800 uppercase">
                            <span class="text-indigo-600 font-black">[${codSeguro}]</span> ${p.nombre}
                        </p>
                        <p class="text-xs text-stone-500 font-semibold">Stock: ${p.stock} | $${p.precio} MXN</p>
                    </div>
                </div>
                <div class="flex gap-1">
                    <button type="button" onclick="abrirModal(${p.id}, '${codSeguro}', '${nomSeguro}', ${p.precio}, ${p.stock}, ${p.categoria_id})" class="text-indigo-500 hover:bg-indigo-100 p-2 rounded-lg transition-colors" title="Editar">✏️</button>
                    <button type="button" onclick="borrarPantalonDefinitivo(${p.id})" class="text-rose-500 hover:bg-rose-100 p-2 rounded-lg transition-colors" title="Borrar">🗑️</button>
                </div>
            `;
            contenedor.appendChild(div);
        });
    } catch (error) { 
        console.error("Error del Inventario:", error); 
    }
}

async function borrarPantalonDefinitivo(id) {
    if(!confirm("¿Estás seguro de borrar este modelo para siempre?")) return;
    
    try { 
        const respuesta = await fetch(`${API_URL}/pantalones/${id}`, {
            method: 'DELETE', 
            headers: obtenerTokenHeader()
        });
        
        if(respuesta.ok) {
            cargarInventarioAdmin(); 
        } else {
            alert("Error al intentar eliminar el pantalón.");
        }
    } catch(e) {
        console.error(e);
    }
}

// ==========================================
// 8. MODAL DE EDICIÓN FLOTANTE
// ==========================================
function abrirModal(id, codigo, nombre, precio, stock, categoria_id) {
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-codigo').value = codigo;
    document.getElementById('edit-nombre').value = nombre;
    document.getElementById('edit-precio').value = precio;
    document.getElementById('edit-stock').value = stock;
    document.getElementById('edit-categoria').value = categoria_id;
    document.getElementById('edit-foto').value = '';
    
    document.getElementById('modal-editar').classList.remove('hidden');
}

function cerrarModal() { 
    document.getElementById('modal-editar').classList.add('hidden'); 
}

document.getElementById('formulario-editar').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('edit-id').value;
    const btn = e.target.querySelector('button[type="submit"]'); 
    
    btn.innerText = "Guardando..."; 
    btn.disabled = true;
    
    const formData = new FormData();
    formData.append('codigo', document.getElementById('edit-codigo').value);
    formData.append('nombre', document.getElementById('edit-nombre').value);
    formData.append('precio', document.getElementById('edit-precio').value);
    formData.append('stock', document.getElementById('edit-stock').value);
    formData.append('categoria_id', document.getElementById('edit-categoria').value);
    
    const foto = document.getElementById('edit-foto').files[0]; 
    if(foto) {
        formData.append('foto', foto);
    }

    try {
        const respuesta = await fetch(`${API_URL}/pantalones/${id}`, {
            method: 'PUT', 
            headers: obtenerTokenHeader(), 
            body: formData
        });
        
        if(respuesta.ok) {
            alert("Pantalón actualizado correctamente.");
            cerrarModal(); 
            cargarInventarioAdmin();
        } else { 
            alert('Error al actualizar. Posiblemente sesión caducada.');
        }
    } catch (e) {
        console.error("Error al editar:", e);
    } finally { 
        btn.innerText = "GUARDAR CAMBIOS"; 
        btn.disabled = false; 
    }
}); // <-- ¡AQUÍ ES DONDE FALTABA CERRAR EL BLOQUE ANTERIOR!

// ==========================================
// 9. RESPALDOS DE SEGURIDAD (GLOBAL)
// ==========================================
// Esta función ahora vive libre en el espacio global y los botones ya la pueden encontrar.
async function descargarBaseDeDatos() {
    try {
        const respuesta = await fetch(`${API_URL}/backup/descargar`, {
            method: 'GET',
            headers: obtenerTokenHeader()
        });

        if (!respuesta.ok) {
            alert("No se pudo descargar el respaldo. Verifica tu sesión.");
            return;
        }

        // Magia para descargar el archivo JSON en el navegador
        const blob = await respuesta.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        
        // Nombra el archivo con la fecha de hoy
        const fecha = new Date().toISOString().split('T')[0];
        link.download = `SurpriseJeans_Respaldo_${fecha}.json`;
        
        document.body.appendChild(link);
        link.click();
        
        // Limpiamos la memoria
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        console.error("Error al descargar el respaldo:", error);
        alert("Hubo un problema de conexión al generar el respaldo.");
    }
}

// ==========================================
// 10. CARGA MÁGICA DE FOTOS (NIVEL HACKER)
// ==========================================
async function procesarFotosMagicas() {
    const inputFotos = document.getElementById('fotos-magicas');
    const archivos = inputFotos.files;
    const btnMagico = document.getElementById('btn-magico');

    if (archivos.length === 0) {
        alert("Por favor, selecciona al menos una foto.");
        return;
    }

    // Pon aquí tu API Key de ImgBB (Consíguela en api.imgbb.com)
    const IMGBB_API_KEY = '967d4560b8e4d58a4f50db487013722f'; 
    
    btnMagico.innerHTML = 'Subiendo a la nube... ⏳';
    btnMagico.disabled = true;

    // Empezamos a armar el texto del Excel en la memoria
    let csvVirtual = "Codigo,Nombre,Precio,Stock,Categoria,Foto_URL\n";
    let exitos = 0;

    try {
        for (let i = 0; i < archivos.length; i++) {
            const archivo = archivos[i];

            // 🛡️ ESCUDO: Si el archivo oculto no es una imagen, lo saltamos automáticamente
            if (!archivo.type.startsWith('image/')) continue;

            const nombreSinExtension = archivo.name.split('.')[0];
            const partes = nombreSinExtension.split('_'); // Separa por guiones bajos
            

            // Validamos que el nombre tenga el formato SKU_Nombre_Precio
            if (partes.length < 3) {
                console.warn(`Se saltó ${archivo.name}: El nombre no tiene el formato correcto.`);
                continue; 
            }

            const sku = partes[0];
            const nombre = partes[1].replace(/([a-z])([A-Z])/g, '$1 $2');
            const precio = partes[2];

            // 1. Subimos la foto a ImgBB directamente desde el navegador
            const fdImg = new FormData();
            fdImg.append('image', archivo);

            const respuestaImg = await fetch(`https://api.imgbb.com/1/upload?key=${IMGBB_API_KEY}`, {
                method: 'POST',
                body: fdImg
            });

            const dataImg = await respuestaImg.json();
            
            if (dataImg.success) {
                const urlDirecta = dataImg.data.url;
                // 2. Agregamos este modelo a nuestro Excel virtual (Stock 0 por defecto)
                csvVirtual += `${sku},${nombre},${precio},0,Nuevos,${urlDirecta}\n`;
                exitos++;
            }
        }

        if (exitos === 0) {
            alert("Ninguna foto tenía el formato correcto (SKU_Nombre_Precio.jpg).");
            return;
        }

        btnMagico.innerHTML = 'Sincronizando catálogo... ⚙️';

        // 3. Empaquetamos nuestro Excel virtual y se lo mandamos a tu servidor web
        const blobCSV = new Blob([csvVirtual], { type: 'text/csv' });
        const formDataFinal = new FormData();
        formDataFinal.append('archivo', blobCSV, 'catalogo_magico.csv');

        const respuestaBackend = await fetch(`${API_URL}/pantalones/excel`, {
            method: 'POST',
            headers: obtenerTokenHeader(), // Usa tu token de admin
            body: formDataFinal
        });

        const dataBackend = await respuestaBackend.json();

        if (respuestaBackend.ok) {
            alert(`¡Magia completada! ✨\nSe subieron y procesaron ${exitos} fotos nuevas.\n\nEl servidor dice: ${dataBackend.mensaje}`);
            cargarInventarioAdmin(); // Refresca la tabla
            inputFotos.value = ''; // Limpia el input
        } else {
            alert(`Error del servidor: ${dataBackend.detail || dataBackend.error}`);
        }

    } catch (error) {
        console.error("Error en la carga mágica:", error);
        alert("Hubo un problema de red. Revisa tu conexión.");
    } finally {
        btnMagico.innerHTML = '<span>🚀</span> SUBIR FOTOS';
        btnMagico.disabled = false;
    }
}