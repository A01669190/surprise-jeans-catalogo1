// 1. FUNCIÓN DE SEGURIDAD - ¡Ahora está libre y hasta arriba!
function verificarAcceso() {
    const input = document.getElementById('input-password').value;
    const passwordCorrecta = 'yessica2026'; // <-- ¡Cambia tu contraseña aquí si quieres!

    if (input === passwordCorrecta) {
        // Desvanece la pantalla de bloqueo y la oculta
        const panel = document.getElementById('panel-login');
        panel.style.opacity = '0';
        setTimeout(() => {
            panel.style.display = 'none';
        }, 500);
    } else {
        // Muestra el mensaje de error
        document.getElementById('error-password').classList.remove('hidden');
        document.getElementById('input-password').value = ''; // Limpia la cajita
    }
}

// 2. CONFIGURACIÓN DE LA API
const API_URL = 'https://surprise-jeans-api.onrender.com';

document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
});

// 3. FUNCIÓN PARA CARGAR CATEGORÍAS EN EL SELECT
async function cargarCategoriasEnSelect() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        const select = document.getElementById('categoria');
        
        // Limpiamos el select por si se acaba de agregar una nueva
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
    
    // Usamos FormData porque tu API requiere Form(...)
    const formData = new FormData();
    formData.append('nombre', document.getElementById('nueva-categoria').value);

    try {
        const respuesta = await fetch(`${API_URL}/categorias`, {
            method: 'POST',
            body: formData
        });

        if (respuesta.ok) {
            alert('¡Categoría creada con éxito!');
            document.getElementById('nueva-categoria').value = '';
            // Recargamos el select para que aparezca la nueva opción
            cargarCategoriasEnSelect(); 
        } else {
            alert('Hubo un error al crear la categoría.');
        }
    } catch (error) {
        console.error("Error:", error);
    }
});

// 5. FUNCIÓN PARA SUBIR PANTALONES AL CATÁLOGO
document.getElementById('formulario-admin').addEventListener('submit', async (e) => {
    e.preventDefault(); 

    const formData = new FormData();
    formData.append('nombre', document.getElementById('nombre').value);
    formData.append('precio', document.getElementById('precio').value);
    formData.append('categoria_id', document.getElementById('categoria').value);
    formData.append('foto', document.getElementById('foto').files[0]);

    try {
        const respuesta = await fetch(`${API_URL}/pantalones`, {
            method: 'POST',
            body: formData
        });

        if (respuesta.ok) {
            alert('¡Listo! El pantalón ya está en el catálogo público.');
            document.getElementById('formulario-admin').reset(); 
        } else {
            alert('Hubo un error al guardar.');
        }
    } catch (error) {
        console.error("Error al enviar:", error);
    }
});