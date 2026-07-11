const API_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', () => {
    cargarCategoriasEnSelect();
});

// Función para llenar el menú desplegable
async function cargarCategoriasEnSelect() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        const select = document.getElementById('categoria');
        
        categorias.forEach(cat => {
            const opcion = document.createElement('option');
            opcion.value = cat.id; // El ID oculto
            opcion.textContent = cat.nombre; // El nombre visible
            select.appendChild(opcion);
        });
    } catch (error) {
        console.error("Error al cargar categorías:", error);
    }
}

// Función para enviar los datos al darle click a Guardar
document.getElementById('formulario-admin').addEventListener('submit', async (e) => {
    e.preventDefault(); // Evita que la página parpadee o se recargue

    // FormData nos permite agrupar textos e imágenes al mismo tiempo
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
            document.getElementById('formulario-admin').reset(); // Limpia los campos
        } else {
            alert('Hubo un error al guardar.');
        }
    } catch (error) {
        console.error("Error al enviar:", error);
    }
});