// 1. CONFIGURACIÓN DE LA API
const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

// ==========================================
// 2. SISTEMA DE LOGIN REAL CON BACKEND (JWT)
// ==========================================
async function verificarAcceso() {
    const inputPassword = document.getElementById('input-password').value;
    
    // Armamos la petición de seguridad para el backend en Python
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
            // Guardamos el token criptográfico en la memoria secreta del navegador
            sessionStorage.setItem('token_vip', data.access_token); 
            
            // Ocultamos el panel de bloqueo
            const panel = document.getElementById('panel-login');
            panel.style.opacity = '0';
            setTimeout(() => { panel.style.display = 'none'; }, 500);
        } else {
            // Contraseña incorrecta
            document.getElementById('error-password').classList.remove('hidden');
            document.getElementById('input-password').value = ''; 
        }
    } catch (error) {
        console.error("Error al iniciar sesión:", error);
    }
}

// FUNCIÓN CLAVE: Obtiene el token para enviarlo como "Gafete VIP" en cada petición protegida
function obtenerTokenHeader() {
    const token = sessionStorage.getItem('token_vip');
    return { 'Authorization': `Bearer ${token}` };
}

// ==========================================
// 3. INICIALIZACIÓN
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
    cargarInventarioAdmin(); // Carga la lista de inventario al entrar
});

async function cargarCategoriasEnSelect() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        const select = document.getElementById('categoria');
        
        select.innerHTML = ''; 
        categorias.forEach(cat => {
            const opcion = document.createElement('option');
            opcion.value = cat.id; 
            opcion.textContent = cat.nombre; 
            select.appendChild(opcion);
        });
    } catch (error) {
        console.error("Error al cargar categorías:", error);
    }
}

// ==========================================
// 4. CREAR UNA NUEVA CATEGORÍA (Protegido)
// ==========================================
document.getElementById('formulario-categoria').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('nombre', document.getElementById('nueva-categoria').value);

    try {
        const respuesta = await fetch(`${API_URL}/categorias`, { 
            method: 'POST', 
            headers: obtenerTokenHeader(), // <-- Enviamos el Token de Seguridad
            body: formData 
        });
        if (respuesta.ok) {
            alert('¡Categoría creada con éxito!');
            document.getElementById('nueva-categoria').value = '';
            cargarCategoriasEnSelect(); 
        } else {
            alert('Error: No tienes autorización o tu sesión ha caducado. Recarga la página.');
        }
    } catch (error) { console.error("Error:", error); }
});

// ==========================================
// 5. SISTEMA DE CARGA MÚLTIPLE (COLA)
// ==========================================
let pantalonesEnCola = [];

// A. Añadir al carrito temporal (No requiere internet aún)
document.getElementById('formulario-admin').addEventListener('submit', (e) => {
    e.preventDefault();
    
    const nombre = document.getElementById('nombre').value;
    const precio = document.getElementById('precio').value;
    const stock = document.getElementById('stock').value;
    const categoriaSelect = document.getElementById('categoria');
    const categoriaNombre = categoriaSelect.options[categoriaSelect.selectedIndex].text;
    const categoria_id = categoriaSelect.value;
    const fotoInput = document.getElementById('foto');
    const fotoFile = fotoInput.files[0];

    if(!fotoFile) return;

    pantalonesEnCola.push({
        nombre: nombre,
        precio: precio,
        stock: stock,
        categoria_id: categoria_id,
        categoriaNombre: categoriaNombre,
        foto: fotoFile
    });

    document.getElementById('formulario-admin').reset(); 
    // Restaurar el valor de stock a 1 por defecto
    document.getElementById('stock').value = 1;
    actualizarUICola(); 
});

// B. Dibujar la lista visual de la cola
function actualizarUICola() {
    const lista = document.getElementById('lista-cola');
    const contador = document.getElementById('contador-cola');
    const btnSubir = document.getElementById('btn-subir-todos');

    lista.innerHTML = '';
    contador.innerText = pantalonesEnCola.length;

    if(pantalonesEnCola.length > 0) {
        btnSubir.classList.remove('hidden');
    } else {
        btnSubir.classList.add('hidden');
    }

    pantalonesEnCola.forEach((pantalon, index) => {
        const li = document.createElement('li');
        li.className = 'py-3 flex justify-between items-center text-sm';
        li.innerHTML = `
            <div>
                <span class="font-bold text-gray-800">${pantalon.nombre}</span> 
                <span class="text-gray-500">($${pantalon.precio}) - ${pantalon.categoriaNombre} | Stock: ${pantalon.stock}</span>
            </div>
            <button onclick="eliminarDeCola(${index})" class="text-rose-500 hover:bg-rose-100 hover:text-rose-700 rounded-full w-6 h-6 flex items-center justify-center font-bold text-lg transition-colors pb-1" title="Quitar de la lista">×</button>
        `;
        lista.appendChild(li);
    });
}

// C. Quitar de la cola
function eliminarDeCola(index) {
    pantalonesEnCola.splice(index, 1);
    actualizarUICola();
}

// D. Mandar todo de golpe al servidor (Protegido con Token)
async function subirTodos() {
    const btnSubir = document.getElementById('btn-subir-todos');
    btnSubir.innerText = 'Subiendo archivos, por favor espera...';
    btnSubir.disabled = true;
    btnSubir.classList.replace('bg-indigo-600', 'bg-indigo-400');

    let subidosExito = 0;

    for (let i = 0; i < pantalonesEnCola.length; i++) {
        const p = pantalonesEnCola[i];
        const formData = new FormData();
        formData.append('nombre', p.nombre);
        formData.append('precio', p.precio);
        formData.append('stock', p.stock);
        formData.append('categoria_id', p.categoria_id);
        formData.append('foto', p.foto);

        try {
            const respuesta = await fetch(`${API_URL}/pantalones`, {
                method: 'POST',
                headers: obtenerTokenHeader(), // <-- Enviamos el Token de Seguridad
                body: formData
            });
            if (respuesta.ok) subidosExito++;
            else console.error("Error de autorización al subir", p.nombre);
        } catch (error) {
            console.error("Error de red al subir:", p.nombre, error);
        }
    }

    if(subidosExito > 0) {
        alert(`¡Inventario actualizado! Se subieron ${subidosExito} modelos con éxito al catálogo.`);
    } else {
        alert(`Error: No se pudo subir nada. Verifica tu sesión o contraseña.`);
    }
    
    pantalonesEnCola = [];
    actualizarUICola();
    cargarInventarioAdmin(); // Recarga la lista de abajo para mostrar los nuevos
    
    btnSubir.innerText = '🚀 SUBIR TODOS AL CATÁLOGO';
    btnSubir.disabled = false;
    btnSubir.classList.replace('bg-indigo-400', 'bg-indigo-600');
}

// ==========================================
// 6. GESTOR DE INVENTARIO ACTUAL
// ==========================================

// Cargar lo que ya existe en la base de datos (Público, no requiere token)
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
            div.innerHTML = `
                <div class="flex items-center gap-4">
                    <img src="${p.imagen_url}" class="w-12 h-12 object-cover rounded-md shadow-sm">
                    <div>
                        <p class="font-bold text-sm text-gray-800 uppercase">${p.nombre}</p>
                        <p class="text-xs text-indigo-600 font-semibold">Stock: ${p.stock} <span class="text-stone-400 font-normal">| $${p.precio} MXN</span></p>
                    </div>
                </div>
                <button onclick="borrarPantalonDefinitivo(${p.id})" class="text-rose-500 hover:text-rose-700 hover:bg-rose-100 p-2 rounded-lg transition-colors" title="Eliminar de la base de datos">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            `;
            contenedor.appendChild(div);
        });
    } catch (error) {
        console.error("Error al cargar inventario:", error);
    }
}

// Función para borrar de la nube (Protegido con Token)
async function borrarPantalonDefinitivo(id) {
    if(!confirm("¿Estás seguro de que quieres borrar este pantalón para siempre? Esto no se puede deshacer.")) return;

    try {
        const respuesta = await fetch(`${API_URL}/pantalones/${id}`, {
            method: 'DELETE',
            headers: obtenerTokenHeader() // <-- Enviamos el Token de Seguridad
        });

        if(respuesta.ok) {
            alert("Pantalón eliminado de la tienda.");
            cargarInventarioAdmin(); // Recarga la lista
        } else {
            alert("Error: No tienes autorización o tu sesión ha caducado. Recarga la página e inicia sesión de nuevo.");
        }
    } catch (error) {
        console.error("Error al borrar:", error);
    }
}