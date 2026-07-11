const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

// Guardamos el inventario en la memoria para no hacer lenta la página
let inventarioGlobal = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarCategorias();
    inicializarTienda(); 
});

// 1. Descarga el catálogo una sola vez al entrar
async function inicializarTienda() {
    try {
        const respuesta = await fetch(`${API_URL}/pantalones`);
        inventarioGlobal = await respuesta.json();
        renderizarPantalones(inventarioGlobal); // Dibuja todos al inicio
    } catch (error) {
        console.error("Error al cargar la tienda:", error);
    }
}

// 2. Dibuja las categorías
async function cargarCategorias() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        
        const contenedor = document.getElementById('contenedor-categorias');
        contenedor.innerHTML = ''; 
        
        const btnTodos = document.createElement('button');
        btnTodos.className = 'bg-stone-800 text-white border border-stone-800 px-5 py-2 rounded-full text-xs uppercase tracking-widest hover:bg-stone-700 transition-all shadow-sm';
        btnTodos.innerText = 'TODOS';
        btnTodos.onclick = () => renderizarPantalones(inventarioGlobal); 
        contenedor.appendChild(btnTodos);

        categorias.forEach(categoria => {
            const boton = document.createElement('button');
            boton.className = 'bg-white border border-rose-100 text-stone-500 px-5 py-2 rounded-full text-xs uppercase tracking-widest hover:border-rose-300 hover:text-stone-800 transition-all shadow-sm';
            boton.innerText = categoria.nombre;
            
            // Filtro por categoría desde la memoria
            boton.onclick = () => {
                const filtrados = inventarioGlobal.filter(p => p.categoria_id === categoria.id);
                renderizarPantalones(filtrados);
                document.getElementById('buscador-tienda').value = ''; // Limpia el buscador si usas botones
            };
            
            contenedor.appendChild(boton);
        });
    } catch (error) {
        console.error("Error al cargar categorías:", error);
    }
}

// ==========================================
// 3. EL BUSCADOR EN TIEMPO REAL
// ==========================================
// Escucha cada vez que el usuario teclea una letra
document.getElementById('buscador-tienda').addEventListener('input', (e) => {
    const textoBuscado = e.target.value.toLowerCase();
    
    // Filtra instantáneamente buscando coincidencias en el nombre del pantalón
    const pantalonesFiltrados = inventarioGlobal.filter(pantalon => 
        pantalon.nombre.toLowerCase().includes(textoBuscado)
    );
    
    renderizarPantalones(pantalonesFiltrados);
});

// ==========================================
// 4. MOTOR GRÁFICO (Dibuja las tarjetas)
// ==========================================
function renderizarPantalones(listaPantalones) {
    const contenedor = document.getElementById('contenedor-pantalones');
    contenedor.innerHTML = ''; 
    
    if (listaPantalones.length === 0) {
        contenedor.innerHTML = '<p class="col-span-full text-center text-stone-400 py-10 font-medium">No encontramos ningún modelo con esa búsqueda 😔</p>';
        return;
    }

    listaPantalones.forEach((pantalon, index) => {
        const tarjeta = document.createElement('div');
        tarjeta.className = 'group flex flex-col cursor-pointer';
        
        let imageUrl = pantalon.imagen_url;
        if (imageUrl && imageUrl.includes('localhost:8000')) {
            imageUrl = imageUrl.replace('http://localhost:8000', '');
        }
        
        const imageUrlDefinitiva = imageUrl && imageUrl.startsWith('http') 
            ? imageUrl 
            : `${API_URL}${imageUrl && imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
        
        // --- LÓGICA DE STOCK Y ETIQUETAS VISUALES ---
        let etiqueta = '';
        let claseImagen = 'absolute top-0 left-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-in-out';
        
        let botonAccion = `
            <a href="https://wa.me/525581410686?text=Hola! Me encantó el modelo ${pantalon.nombre}. ¿Tienen disponibilidad?" target="_blank" class="bg-stone-900 text-white hover:bg-rose-500 hover:text-white px-4 py-2 rounded-full text-xs font-semibold tracking-wider transition-colors shadow-md">
                COMPRAR
            </a>
        `;

        if (pantalon.stock === 0) {
            etiqueta = '<span class="absolute top-3 left-3 bg-rose-600 text-white text-xs font-black px-3 py-1 rounded-full shadow-md tracking-wider z-10">AGOTADO</span>';
            claseImagen += ' grayscale opacity-60'; 
            botonAccion = `
                <button disabled class="bg-stone-200 text-stone-400 px-4 py-2 rounded-full text-xs font-semibold tracking-wider cursor-not-allowed">
                    SIN STOCK
                </button>
            `;
        } else if (index >= listaPantalones.length - 5) {
            etiqueta = '<span class="absolute top-3 left-3 bg-indigo-600 text-white text-xs font-black px-3 py-1 rounded-full shadow-md tracking-wider z-10">NUEVO ✨</span>';
        }

        tarjeta.innerHTML = `
            <div class="relative pt-[130%] bg-stone-50 rounded-xl overflow-hidden mb-4">
                ${etiqueta}
                <img src="${imageUrlDefinitiva}" alt="${pantalon.nombre}" class="${claseImagen}">
            </div>
            <div class="flex flex-col flex-grow px-1">
                <h3 class="font-serif text-stone-800 text-lg md:text-xl mb-1">${pantalon.nombre}</h3>
                <p class="text-xs text-stone-500 font-light mb-3 line-clamp-2">${pantalon.descripcion || 'Calidad y ajuste perfecto.'}</p>
                <div class="mt-auto flex items-center justify-between">
                    <span class="text-stone-900 font-semibold text-lg">$${pantalon.precio}</span>
                    ${botonAccion}
                </div>
            </div>
        `;
        contenedor.appendChild(tarjeta);
    });
}