const API_URL = 'https://surprise-jeans-api-denz.onrender.com';

// Variables de estado para la paginación y filtros
let offsetGlobal = 0;
const LIMITE = 20; 
let categoriaActiva = null;
let busquedaActiva = '';

document.addEventListener('DOMContentLoaded', () => {
    cargarCategorias();
    cargarPantalones(true); // true = Es una carga nueva, limpia la pantalla
});

// 1. Dibuja las categorías
async function cargarCategorias() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        const contenedor = document.getElementById('contenedor-categorias');
        
        contenedor.innerHTML = '';

        const btnTodos = document.createElement('button');
        btnTodos.className = 'bg-stone-800 text-white border border-stone-800 px-5 py-2 rounded-full text-xs uppercase tracking-widest hover:bg-stone-700 transition-all shadow-sm';
        btnTodos.innerText = 'TODOS';
        btnTodos.onclick = () => {
            categoriaActiva = null;
            busquedaActiva = '';
            document.getElementById('buscador-tienda').value = '';
            cargarPantalones(true); 
        };
        contenedor.appendChild(btnTodos);

        categorias.forEach(categoria => {
            const boton = document.createElement('button');
            boton.className = 'bg-white border border-rose-100 text-stone-500 px-5 py-2 rounded-full text-xs uppercase tracking-widest hover:border-rose-300 hover:text-stone-800 transition-all shadow-sm';
            boton.innerText = categoria.nombre;
            boton.onclick = () => {
                categoriaActiva = categoria.id;
                busquedaActiva = '';
                document.getElementById('buscador-tienda').value = '';
                cargarPantalones(true);
            };
            contenedor.appendChild(boton);
        });
    } catch (error) {
        console.error("Error al cargar categorías:", error);
    }
}

// 2. Buscador con Temporizador (Evita saturar la base de datos al teclear rápido)
let temporizadorBuscador;
document.getElementById('buscador-tienda').addEventListener('input', (e) => {
    clearTimeout(temporizadorBuscador);
    // Espera 300ms después de que el usuario deja de escribir para buscar
    temporizadorBuscador = setTimeout(() => {
        busquedaActiva = e.target.value.trim();
        cargarPantalones(true);
    }, 300); 
});

// 3. Botón Cargar Más
document.getElementById('btn-cargar-mas').addEventListener('click', () => {
    cargarPantalones(false); // false = Añade tarjetas abajo sin borrar las que ya están
});

// 4. El motor que habla con PostgreSQL (Backend)
async function cargarPantalones(esNuevaBusqueda) {
    if (esNuevaBusqueda) {
        offsetGlobal = 0; // Reiniciamos el contador
        document.getElementById('contenedor-pantalones').innerHTML = ''; // Limpiamos pantalla
    }

    try {
        // Armamos la URL exacta con los parámetros de paginación y filtros
        let url = `${API_URL}/pantalones?skip=${offsetGlobal}&limit=${LIMITE}`;
        if (categoriaActiva) url += `&categoria_id=${categoriaActiva}`;
        if (busquedaActiva) url += `&busqueda=${busquedaActiva}`;

        const respuesta = await fetch(url);
        const pantalones = await respuesta.json();
        
        renderizarPantalones(pantalones, esNuevaBusqueda);

        // Lógica para mostrar u ocultar el botón de "Cargar Más"
        const btnCargarMas = document.getElementById('btn-cargar-mas');
        if (pantalones.length === LIMITE) {
            btnCargarMas.classList.remove('hidden');
            offsetGlobal += LIMITE; // Preparamos el salto para la siguiente petición
        } else {
            btnCargarMas.classList.add('hidden'); // Ocultamos el botón si ya no hay más
        }

    } catch (error) {
        console.error("Error al cargar la tienda:", error);
    }
}

// 5. Motor Gráfico de Tarjetas
function renderizarPantalones(listaPantalones, esNuevaBusqueda) {
    
    const contenedor = document.getElementById('contenedor-pantalones');
    
    if (listaPantalones.length === 0 && esNuevaBusqueda) {
        contenedor.innerHTML = '<p class="col-span-full text-center text-stone-400 py-10 font-medium">No encontramos resultados 😔</p>';
        return;
    }

    listaPantalones.forEach((pantalon, index) => {
        const tarjeta = document.createElement('div');
        tarjeta.className = 'group flex flex-col cursor-pointer';
        
        let imageUrl = pantalon.imagen_url;
        if (imageUrl && imageUrl.includes('localhost:8000')) {
            imageUrl = imageUrl.replace('http://localhost:8000', '');
        }
        // Si el pantalón tiene tallas, dibuja los botones
        const botonesTallas = pantalon.tallas && pantalon.tallas.length > 0 ? `
            <div class="mt-3 mb-2 border-t border-gray-100 pt-3">
                <p class="text-[10px] uppercase text-gray-500 font-bold mb-2 tracking-wider">Selecciona tu talla:</p>
                <div class="flex flex-wrap gap-1.5">
                    ${pantalon.tallas.map(t => `
                        <button type="button" 
                                class="w-8 h-8 rounded-md border border-gray-200 text-[11px] font-black text-gray-700 hover:border-indigo-600 hover:text-indigo-600 focus:bg-indigo-600 focus:border-indigo-600 focus:text-white transition-all shadow-sm"
                                onclick="seleccionarTalla('${pantalon.codigo}', '${t.talla}', '${t.sku}')">
                            ${t.talla}
                        </button>
                    `).join('')}
                </div>
            </div>
        ` : '';

        const imageUrlDefinitiva = imageUrl && imageUrl.startsWith('http') 
            ? imageUrl 
            : `${API_URL}${imageUrl && imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
        
        let etiqueta = '';
        let claseImagen = 'absolute top-0 left-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-in-out';
        
        let botonAccion = `
            <a href="https://wa.me/525581410686?text=Hola! Me encantó el modelo ${pantalon.nombre}. ¿Tienen disponibilidad?" target="_blank" class="bg-stone-900 text-white hover:bg-rose-500 hover:text-white px-4 py-2 rounded-full text-xs font-semibold tracking-wider transition-colors shadow-md">
                COMPRAR
            </a>
        `;

        // Etiqueta de Agotado
        if (pantalon.stock === 0) {
            etiqueta = '<span class="absolute top-3 left-3 bg-rose-600 text-white text-xs font-black px-3 py-1 rounded-full shadow-md tracking-wider z-10">AGOTADO</span>';
            claseImagen += ' grayscale opacity-60'; 
            botonAccion = `
                <button disabled class="bg-stone-200 text-stone-400 px-4 py-2 rounded-full text-xs font-semibold tracking-wider cursor-not-allowed">
                    SIN STOCK
                </button>
            `;
        } 
        // Etiqueta de Nuevo
        else if (index < 5 && offsetGlobal === 0 && esNuevaBusqueda && !busquedaActiva && !categoriaActiva) {
            etiqueta = '<span class="absolute top-3 left-3 bg-indigo-600 text-white text-xs font-black px-3 py-1 rounded-full shadow-md tracking-wider z-10">NUEVO ✨</span>';
        }

        // AQUÍ SE INYECTA TODO JUNTO EN LA TARJETA 
        tarjeta.innerHTML = `
            <div class="relative pt-[130%] bg-stone-50 rounded-xl overflow-hidden mb-4">
                ${etiqueta}
                <img src="${imageUrlDefinitiva}" alt="${pantalon.nombre}" class="${claseImagen}" loading="lazy">
            </div>
            <div class="flex flex-col flex-grow px-1">
                <h3 class="font-serif text-stone-800 text-lg md:text-xl mb-1">${pantalon.nombre}</h3>
                <p class="text-xs text-stone-500 font-light mb-3 line-clamp-2">${pantalon.descripcion || 'Calidad y ajuste perfecto.'}</p>
                
                ${botonesTallas} 

                <div class="mt-auto flex items-center justify-between pt-2">
                    <span class="text-stone-900 font-semibold text-lg">$${pantalon.precio}</span>
                    ${botonAccion}
                </div>
            </div>
        `;
        contenedor.appendChild(tarjeta);
    });
}