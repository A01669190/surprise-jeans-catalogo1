const API_URL = 'https://surprise-jeans-api.onrender.com';

document.addEventListener('DOMContentLoaded', () => {
    cargarCategorias();
    cargarPantalones();
});

async function cargarCategorias() {
    try {
        const respuesta = await fetch(`${API_URL}/categorias`);
        const categorias = await respuesta.json();
        
        const contenedor = document.getElementById('contenedor-categorias');
        
        categorias.forEach(categoria => {
            const boton = document.createElement('button');
            boton.className = 'bg-white border border-rose-100 text-stone-500 px-5 py-2 rounded-full text-xs uppercase tracking-widest hover:border-rose-300 hover:text-stone-800 transition-all shadow-sm';
            boton.innerText = categoria.nombre;
            contenedor.appendChild(boton);
        });
    } catch (error) {
        console.error("Error al cargar categorías:", error);
    }
}

async function cargarPantalones() {
    try {
        const respuesta = await fetch(`${API_URL}/pantalones`);
        const pantalones = await respuesta.json();
        
        const contenedor = document.getElementById('contenedor-pantalones');
        contenedor.innerHTML = ''; 
        
        pantalones.forEach(pantalon => {
            const tarjeta = document.createElement('div');
            tarjeta.className = 'group flex flex-col cursor-pointer';
            
            // CORRECCIÓN: Limpiamos el 'localhost' si existe por los registros viejos
            let imageUrl = pantalon.imagen_url;
            if (imageUrl.includes('localhost:8000')) {
                imageUrl = imageUrl.replace('http://localhost:8000', '');
            }
            
            const imageUrlDefinitiva = imageUrl.startsWith('http') 
                ? imageUrl 
                : `${API_URL}${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
            
            tarjeta.innerHTML = `
                <div class="relative pt-[130%] bg-stone-50 rounded-xl overflow-hidden mb-4">
                    <img src="${imageUrlDefinitiva}" alt="${pantalon.nombre}" class="absolute top-0 left-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-in-out">
                </div>
                <div class="flex flex-col flex-grow px-1">
                    <h3 class="font-serif text-stone-800 text-lg md:text-xl mb-1">${pantalon.nombre}</h3>
                    <p class="text-xs text-stone-500 font-light mb-3 line-clamp-2">${pantalon.descripcion || 'Calidad y ajuste perfecto.'}</p>
                    <div class="mt-auto flex items-center justify-between">
                        <span class="text-stone-900 font-semibold text-lg">$${pantalon.precio}</span>
                        <a href="https://wa.me/525581410686?text=Hola! Me encantó el modelo ${pantalon.nombre}. ¿Tienen disponibilidad?" target="_blank" class="bg-stone-900 text-white hover:bg-rose-500 hover:text-white px-4 py-2 rounded-full text-xs font-semibold tracking-wider transition-colors shadow-md">
                            COMPRAR
                        </a>
                    </div>
                </div>
            `;
            contenedor.appendChild(tarjeta);
        });
    } catch (error) {
        console.error("Error al cargar pantalones:", error);
    }
}