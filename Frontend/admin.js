// 1. FUNCIÓN DE SEGURIDAD
function verificarAcceso() {
    const input = document.getElementById('input-password').value;
    const passwordCorrecta = 'yessica2026'; 

    if (input === passwordCorrecta) {
        const panel = document.getElementById('panel-login');
        panel.style.opacity = '0';
        setTimeout(() => { panel.style.display = 'none'; }, 500);
    } else {
        document.getElementById('error-password').classList.remove('hidden');
        document.getElementById('input-password').value = ''; 
    }
}

// 2. CONFIGURACIÓN DE LA API
const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
});

// 3. FUNCIÓN PARA CARGAR CATEGORÍAS
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

// 4. FUNCIÓN PARA CREAR UNA NUEVA CATEGORÍA
document.getElementById('formulario-categoria').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('nombre', document.getElementById('nueva-categoria').value);

    try {
        const respuesta = await fetch(`${API_URL}/categorias`, { method: 'POST', body: formData });
        if (respuesta.ok) {
            alert('¡Categoría creada con éxito!');
            document.getElementById('nueva-categoria').value = '';
            cargarCategoriasEnSelect(); 
        } else {
            alert('Hubo un error al crear la categoría.');
        }
    } catch (error) { console.error("Error:", error); }
});

// ==========================================
// NUEVO: SISTEMA DE CARGA MÚLTIPLE
// ==========================================
let pantalonesEnCola = [];

// A. Añadir al carrito temporal (No sube nada a internet todavía)
document.getElementById('formulario-admin').addEventListener('submit', (e) => {
    e.preventDefault();
    
    const nombre = document.getElementById('nombre').value;
    const precio = document.getElementById('precio').value;
    const categoriaSelect = document.getElementById('categoria');
    const categoriaNombre = categoriaSelect.options[categoriaSelect.selectedIndex].text;
    const categoria_id = categoriaSelect.value;
    const fotoInput = document.getElementById('foto');
    const fotoFile = fotoInput.files[0];

    if(!fotoFile) return;

    // Guardar en el arreglo de memoria
    pantalonesEnCola.push({
        nombre: nombre,
        precio: precio,
        categoria_id: categoria_id,
        categoriaNombre: categoriaNombre,
        foto: fotoFile
    });

    document.getElementById('formulario-admin').reset(); 
    actualizarUICola(); 
});

// B. Dibujar la lista visual en la pantalla
function actualizarUICola() {
    const lista = document.getElementById('lista-cola');
    const contador = document.getElementById('contador-cola');
    const btnSubir = document.getElementById('btn-subir-todos');

    lista.innerHTML = '';
    contador.innerText = pantalonesEnCola.length;

    // Muestra u oculta el botón azul gigante
    if(pantalonesEnCola.length > 0) {
        btnSubir.classList.remove('hidden');
    } else {
        btnSubir.classList.add('hidden');
    }

    // Crear un renglón por cada pantalón en la lista
    pantalonesEnCola.forEach((pantalon, index) => {
        const li = document.createElement('li');
        li.className = 'py-3 flex justify-between items-center text-sm';
        li.innerHTML = `
            <div>
                <span class="font-bold text-gray-800">${pantalon.nombre}</span> 
                <span class="text-gray-500">($${pantalon.precio}) - ${pantalon.categoriaNombre}</span>
            </div>
            <button onclick="eliminarDeCola(${index})" class="text-rose-500 hover:bg-rose-100 hover:text-rose-700 rounded-full w-6 h-6 flex items-center justify-center font-bold text-lg transition-colors pb-1" title="Quitar de la lista">×</button>
        `;
        lista.appendChild(li);
    });
}

// C. Quitar de la lista si hay un error
function eliminarDeCola(index) {
    pantalonesEnCola.splice(index, 1);
    actualizarUICola();
}

// D. Mandar todo de golpe al servidor
async function subirTodos() {
    const btnSubir = document.getElementById('btn-subir-todos');
    btnSubir.innerText = 'Subiendo archivos, por favor espera...';
    btnSubir.disabled = true;
    btnSubir.classList.replace('bg-indigo-600', 'bg-indigo-400'); // Cambia color para indicar que está trabajando

    let subidosExito = 0;

    // Envía uno por uno automáticamente
    for (let i = 0; i < pantalonesEnCola.length; i++) {
        const p = pantalonesEnCola[i];
        const formData = new FormData();
        formData.append('nombre', p.nombre);
        formData.append('precio', p.precio);
        formData.append('categoria_id', p.categoria_id);
        formData.append('foto', p.foto);

        try {
            const respuesta = await fetch(`${API_URL}/pantalones`, {
                method: 'POST',
                body: formData
            });
            if (respuesta.ok) subidosExito++;
        } catch (error) {
            console.error("Error al subir:", p.nombre, error);
        }
    }

    alert(`¡Inventario actualizado! Se subieron ${subidosExito} modelos con éxito al catálogo.`);
    
    // Dejar todo como nuevo
    pantalonesEnCola = [];
    actualizarUICola();
    
    // Restaurar el botón
    btnSubir.innerText = '🚀 SUBIR TODOS AL CATÁLOGO';
    btnSubir.disabled = false;
    btnSubir.classList.replace('bg-indigo-400', 'bg-indigo-600');
}