// 1. CONFIGURACIÓN DE LA API
const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

// ==========================================
// 2. SISTEMA DE LOGIN REAL CON BACKEND (JWT)
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
    } catch (error) { console.error("Error al iniciar sesión:", error); }
}

function obtenerTokenHeader() {
    return { 'Authorization': `Bearer ${sessionStorage.getItem('token_vip')}` };
}

// ==========================================
// 3. INICIALIZACIÓN Y GESTIÓN DE CATEGORÍAS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
    cargarInventarioAdmin(); 
});

async function cargarCategoriasEnSelect() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        
        const select = document.getElementById('categoria');
        const selectEdit = document.getElementById('edit-categoria'); 
        const listaAdmin = document.getElementById('lista-categorias-admin'); 
        
        if(select) select.innerHTML = ''; 
        if(selectEdit) selectEdit.innerHTML = '';
        if(listaAdmin) listaAdmin.innerHTML = ''; 

        categorias.forEach(cat => {
            if(select) {
                const opcion = document.createElement('option');
                opcion.value = cat.id; opcion.textContent = cat.nombre; 
                select.appendChild(opcion);
            }
            if(selectEdit) {
                const opEdit = document.createElement('option');
                opEdit.value = cat.id; opEdit.textContent = cat.nombre;
                selectEdit.appendChild(opEdit);
            }
            if(listaAdmin) {
                const li = document.createElement('li');
                li.className = 'bg-gray-50 text-gray-700 text-xs font-semibold px-3 py-1.5 rounded-full flex items-center gap-2 border border-gray-200 shadow-sm';
                li.innerHTML = `
                    ${cat.nombre}
                    <button type="button" onclick="borrarCategoria(${cat.id})" class="text-rose-500 hover:text-white hover:bg-rose-500 rounded-full w-4 h-4 flex items-center justify-center transition-colors" title="Eliminar categoría">×</button>
                `;
                listaAdmin.appendChild(li);
            }
        });
    } catch (error) { console.error("Error al cargar categorías:", error); }
}

document.getElementById('formulario-categoria').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('nombre', document.getElementById('nueva-categoria').value);

    try {
        const respuesta = await fetch(`${API_URL}/categorias`, { 
            method: 'POST', headers: obtenerTokenHeader(), body: formData 
        });
        if (respuesta.ok) {
            alert('¡Categoría creada con éxito!');
            document.getElementById('nueva-categoria').value = '';
            cargarCategoriasEnSelect(); 
        } else { alert('Error: Sesión caducada.'); }
    } catch (error) { console.error("Error:", error); }
});

async function borrarCategoria(id) {
    if(!confirm("¿Estás seguro de que quieres borrar esta categoría?")) return;
    try {
        const respuesta = await fetch(`${API_URL}/categorias/${id}`, {
            method: 'DELETE',
            headers: obtenerTokenHeader()
        });
        if (respuesta.ok) {
            cargarCategoriasEnSelect();
        } else {
            const errorData = await respuesta.json();
            alert(`No se pudo borrar: ${errorData.detail || 'Error de conexión'}`);
        }
    } catch (error) { console.error("Error al borrar categoría:", error); }
}

// ==========================================
// 4. CARGA MASIVA POR EXCEL
// ==========================================
const formExcel = document.getElementById('formulario-excel');
if(formExcel) {
    formExcel.addEventListener('submit', async (e) => {
        e.preventDefault();
        const archivoInput = document.getElementById('archivo-excel');
        const archivo = archivoInput.files[0];
        const btnSubir = document.getElementById('btn-subir-excel');

        if (!archivo) return;

        btnSubir.innerText = 'Procesando...';
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
                archivoInput.value = '';
                cargarCategoriasEnSelect(); 
                cargarInventarioAdmin(); 
            } else {
                alert(`Error: ${data.error || 'Sesión caducada'}`);
            }
        } catch (error) {
            console.error("Error al procesar Excel:", error);
            alert("Ocurrió un error al intentar procesar el archivo.");
        } finally {
            btnSubir.innerText = 'PROCESAR';
            btnSubir.disabled = false;
        }
    });
}

function descargarPlantilla() {
    const contenido = "Nombre,Precio,Stock,Categoria,Foto_URL\nSkinny Azul,150,10,Skinny,https://ejemplo.com/foto1.jpg\nMom Jeans Rotos,180,5,Mom,\nCargo Negro,200,20,Cargo,";
    const blob = new Blob([contenido], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "Plantilla_SurpriseJeans.csv");
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ==========================================
// 5. SISTEMA DE CARGA MANUAL (COLA)
// ==========================================
let pantalonesEnCola = [];

document.getElementById('formulario-admin').addEventListener('submit', (e) => {
    e.preventDefault();
    const nombre = document.getElementById('nombre').value;
    const precio = document.getElementById('precio').value;
    const stock = document.getElementById('stock').value;
    const categoriaSelect = document.getElementById('categoria');
    const categoriaNombre = categoriaSelect.options[categoriaSelect.selectedIndex].text;
    const categoria_id = categoriaSelect.value;
    const fotoFile = document.getElementById('foto').files[0];

    if(!fotoFile) return;

    pantalonesEnCola.push({ nombre, precio, stock, categoria_id, categoriaNombre, foto: fotoFile });
    document.getElementById('formulario-admin').reset(); 
    document.getElementById('stock').value = 1;
    actualizarUICola(); 
});

function actualizarUICola() {
    const lista = document.getElementById('lista-cola');
    const btnSubir = document.getElementById('btn-subir-todos');
    lista.innerHTML = '';
    document.getElementById('contador-cola').innerText = pantalonesEnCola.length;

    if(pantalonesEnCola.length > 0) btnSubir.classList.remove('hidden');
    else btnSubir.classList.add('hidden');

    pantalonesEnCola.forEach((pantalon, index) => {
        const li = document.createElement('li');
        li.className = 'py-3 flex justify-between items-center text-sm';
        li.innerHTML = `
            <div><span class="font-bold">${pantalon.nombre}</span> <span class="text-gray-500">($${pantalon.precio}) - Stock: ${pantalon.stock}</span></div>
            <button type="button" onclick="eliminarDeCola(${index})" class="text-rose-500 hover:bg-rose-100 rounded-full w-6 h-6 font-bold pb-1">×</button>
        `;
        lista.appendChild(li);
    });
}

function eliminarDeCola(index) {
    pantalonesEnCola.splice(index, 1);
    actualizarUICola();
}

async function subirTodos() {
    const btnSubir = document.getElementById('btn-subir-todos');
    btnSubir.innerText = 'Subiendo archivos...';
    btnSubir.disabled = true;
    let subidosExito = 0;

    for (let i = 0; i < pantalonesEnCola.length; i++) {
        const p = pantalonesEnCola[i];
        const formData = new FormData();
        formData.append('nombre', p.nombre); formData.append('precio', p.precio);
        formData.append('stock', p.stock); formData.append('categoria_id', p.categoria_id);
        formData.append('foto', p.foto);

        try {
            const respuesta = await fetch(`${API_URL}/pantalones`, {
                method: 'POST', headers: obtenerTokenHeader(), body: formData
            });
            if (respuesta.ok) subidosExito++;
        } catch (error) { console.error("Error al subir:", p.nombre); }
    }

    if(subidosExito > 0) alert(`¡Se subieron ${subidosExito} modelos con éxito!`);
    
    pantalonesEnCola = [];
    actualizarUICola();
    cargarInventarioAdmin(); 
    btnSubir.innerText = '🚀 SUBIR TODOS AL CATÁLOGO';
    btnSubir.disabled = false;
}

// ==========================================
// 6. GESTOR DE INVENTARIO ACTUAL
// ==========================================
async function cargarInventarioAdmin() {
    try {
        const respuesta = await fetch(`${API_URL}/pantalones`);
        const pantalones = await respuesta.json();
        const contenedor = document.getElementById('lista-inventario');
        contenedor.innerHTML = '';
        
        if(pantalones.length === 0){
            contenedor.innerHTML = '<p class="text-sm text-gray-500 text-center py-4">No hay pantalones en el catálogo.</p>';
            return;
        }

        pantalones.forEach(p => {
            const div = document.createElement('div');
            div.className = 'flex justify-between items-center p-3 bg-gray-50 rounded-lg border border-gray-200';
            
            const nombreSeguro = p.nombre.replace(/'/g, "\\'"); 
            
            div.innerHTML = `
                <div class="flex items-center gap-4">
                    <img src="${p.imagen_url}" class="w-12 h-12 object-cover rounded-md shadow-sm">
                    <div>
                        <p class="font-bold text-sm text-gray-800 uppercase">${p.nombre}</p>
                        <p class="text-xs text-indigo-600 font-semibold">Stock: ${p.stock} <span class="text-stone-400 font-normal">| $${p.precio} MXN</span></p>
                    </div>
                </div>
                <div class="flex gap-1">
                    <button type="button" onclick="abrirModal(${p.id}, '${nombreSeguro}', ${p.precio}, ${p.stock}, ${p.categoria_id})" class="text-indigo-500 hover:text-indigo-700 hover:bg-indigo-100 p-2 rounded-lg transition-colors" title="Editar modelo">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                    </button>
                    <button type="button" onclick="borrarPantalonDefinitivo(${p.id})" class="text-rose-500 hover:text-rose-700 hover:bg-rose-100 p-2 rounded-lg transition-colors" title="Eliminar de la base de datos">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                </div>
            `;
            contenedor.appendChild(div);
        });
    } catch (error) { console.error("Error al cargar inventario:", error); }
}

async function borrarPantalonDefinitivo(id) {
    if(!confirm("¿Estás seguro de que quieres borrar este pantalón para siempre?")) return;
    try {
        const respuesta = await fetch(`${API_URL}/pantalones/${id}`, {
            method: 'DELETE', headers: obtenerTokenHeader()
        });
        if(respuesta.ok) { alert("Pantalón eliminado."); cargarInventarioAdmin(); } 
        else { alert("Error: Sesión caducada."); }
    } catch (error) { console.error("Error al borrar:", error); }
}

// ==========================================
// 7. VENTANA FLOTANTE (EDICIÓN Y ACTUALIZAR FOTO)
// ==========================================
function abrirModal(id, nombre, precio, stock, categoria_id) {
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-nombre').value = nombre;
    document.getElementById('edit-precio').value = precio;
    document.getElementById('edit-stock').value = stock;
    document.getElementById('edit-categoria').value = categoria_id;
    document.getElementById('edit-foto').value = ''; // Limpiamos el input de la foto al abrir
    document.getElementById('modal-editar').classList.remove('hidden');
}

function cerrarModal() {
    document.getElementById('modal-editar').classList.add('hidden');
}

document.getElementById('formulario-editar').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('edit-id').value;
    const btnGuardar = e.target.querySelector('button[type="submit"]');
    
    btnGuardar.innerText = "Guardando...";
    btnGuardar.disabled = true;
    
    const formData = new FormData();
    formData.append('nombre', document.getElementById('edit-nombre').value);
    formData.append('precio', document.getElementById('edit-precio').value);
    formData.append('stock', document.getElementById('edit-stock').value);
    formData.append('categoria_id', document.getElementById('edit-categoria').value);

    // Atrapamos la nueva foto si Yessica decidió actualizarla
    const fotoEdit = document.getElementById('edit-foto').files[0];
    if (fotoEdit) {
        formData.append('foto', fotoEdit);
    }

    try {
        const respuesta = await fetch(`${API_URL}/pantalones/${id}`, {
            method: 'PUT',
            headers: obtenerTokenHeader(),
            body: formData
        });

        if(respuesta.ok) {
            alert('¡Pantalón actualizado con éxito!');
            cerrarModal();
            document.getElementById('edit-foto').value = ''; 
            cargarInventarioAdmin();
        } else {
            alert('Error al actualizar. Verifica tu sesión.');
        }
    } catch (error) { 
        console.error("Error al editar:", error); 
    } finally {
        btnGuardar.innerText = "GUARDAR CAMBIOS";
        btnGuardar.disabled = false;
    }
});