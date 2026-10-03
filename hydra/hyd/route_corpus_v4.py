# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Hyd routing corpus v4: synthetic Spanish requests, decontaminated against the frozen human test.

Each label has many templates; a template is the split unit (train/dev never share one), so dev
measures generalisation to unseen phrasings, not memorised slots. Every candidate is rejected if it
resembles any test sentence: word Jaccard >= 0.3, a shared 4-word span, or two or more of the test's
distinctive words. Style noise (no accents, q/k, no punctuation, typos, openers) is applied per
sentence with a seeded RNG, so the corpus is reproducible from (seed, test hash).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

R = random.Random  # type alias for readability


def pick(rng: R, *options):
    return rng.choice(options)


def num(rng: R, lo: int, hi: int) -> int:
    return rng.randint(lo, hi)


# ---------------------------------------------------------------- templates: label -> [(id, fn)]
def chat(rng: R) -> list:
    occasion = ["la boda de unos amigos", "el bautizo de mi sobrina", "la comunión de mi ahijado",
                "la despedida de soltera de mi prima", "la inauguración de la tienda de mi vecino",
                "el fin de curso de la autoescuela", "la vuelta al cole de mis hijos", "una cena de antiguos alumnos"]
    piece = ["un brindis", "unas palabras", "un discurso cortito", "una tarjeta", "un mensaje"]
    return [
        ("chat-toast", lambda: f"{pick(rng, 'escríbeme', 'prepárame', 'necesito')} {pick(rng, *piece)} para {pick(rng, *occasion)}"),
        ("chat-console", lambda: f"cómo consuelo a {pick(rng, 'una amiga', 'mi vecino', 'un compañero', 'mi tía')} que {pick(rng, 'ha perdido a su perro', 'no ha aprobado las oposiciones', 'se ha quedado sin piso', 'está de bajón')} sin decir tonterías"),
        ("chat-lullaby", lambda: f"invéntate {pick(rng, 'una canción de cuna', 'una nana', 'un cuento para dormir')} sobre {pick(rng, 'un erizo', 'una nube', 'un faro', 'un tractor', 'una ballena')} para {pick(rng, 'mi bebé', 'mi hija pequeña', 'los niños del campamento')}"),
        ("chat-acrostic", lambda: f"hazme un acróstico con el nombre {pick(rng, 'Carmen', 'Iago', 'Noa', 'Brais', 'Rosalía', 'Xoán', 'Olalla')} que sea {pick(rng, 'tierno', 'divertido', 'elegante')}"),
        ("chat-jokes", lambda: f"cuéntame {pick(rng, 'dos', 'tres', 'unos')} chistes {pick(rng, 'malos', 'blancos', 'de los de toda la vida')} sobre {pick(rng, 'dentistas', 'fontaneros', 'pulpos', 'gallegos', 'informáticos')}"),
        ("chat-neighbour", lambda: f"redacta una nota educada para dejar en {pick(rng, 'el buzón', 'el ascensor', 'la puerta')} pidiendo al vecino que {pick(rng, 'no tienda la ropa encima de la mía', 'baje la música por las noches', 'recoja lo de su perro', 'no deje las bicis en el portal')}"),
        ("chat-opinion", lambda: f"qué prefieres tú {pick(rng, 'el mar o la montaña', 'el invierno o el verano', 'los gatos o los perros', 'leer en papel o en el móvil')} y por qué, dime algo con gracia"),
        ("chat-roleplay", lambda: f"haz como si fueras {pick(rng, 'un pirata', 'un abuelo gallego', 'un detective', 'un robot cansado')} y {pick(rng, 'salúdame', 'cuéntame tu día', 'dame un consejo para el lunes')}"),
        ("chat-slogan", lambda: f"dame {pick(rng, 'ideas de eslogan', 'un lema pegadizo', 'frases cortas')} para {pick(rng, 'una peluquería de barrio', 'una frutería', 'un club de ajedrez', 'una academia de inglés', 'un taller de bicis')}"),
        ("chat-thanks", lambda: f"escribe una nota de agradecimiento para {pick(rng, 'la enfermera que cuidó a mi padre', 'el profesor de mi hijo', 'la gente que vino a la mudanza', 'mi entrenador de natación')}"),
        ("chat-explain", lambda: f"explícame de forma sencilla {pick(rng, 'por qué el cielo es azul', 'cómo funciona una hipoteca a grandes rasgos', 'qué es la fotosíntesis', 'por qué se forman las mareas')}, sin rollos"),
        ("chat-excuse", lambda: f"ayúdame a decirle a {pick(rng, 'mi suegra', 'un amigo', 'la presidenta de la comunidad')} que no puedo ir a {pick(rng, 'su cumpleaños', 'la excursión', 'la reunión del sábado')} sin quedar fatal"),
    ]


def coding(rng: R) -> list:
    lang = ["python", "go", "rust", "kotlin", "java", "ruby", "swift", "c#"]
    return [
        ("code-sort", lambda: f"en {pick(rng, *lang)} cómo ordeno una lista de {pick(rng, 'facturas', 'alumnos', 'pedidos', 'eventos')} por {pick(rng, 'fecha', 'importe', 'apellido')} de mayor a menor"),
        ("code-decorator", lambda: f"hazme un decorador en python que {pick(rng, 'mida cuánto tarda una función', 'reintente tres veces si falla', 'guarde en caché el resultado', 'registre los argumentos en un log')}"),
        ("code-pytest", lambda: f"escríbeme tests con {pick(rng, 'pytest', 'unittest', 'jest', 'junit')} para una función que {pick(rng, 'calcula el iva', 'valida un iban', 'convierte grados a fahrenheit', 'divide una cuenta entre amigos')}"),
        ("code-borrow", lambda: f"el compilador de rust me dice {pick(rng, 'que el valor se movió', 'borrowed value does not live long enough', 'cannot borrow as mutable')} y no entiendo por qué, explícamelo"),
        ("code-goroutine", lambda: f"en go cómo {pick(rng, 'espero a que terminen varias goroutines', 'cierro bien un canal', 'pongo un timeout a una petición http', 'leo un fichero línea a línea')}"),
        ("code-pandas", lambda: f"con pandas cómo {pick(rng, 'agrupo por mes y sumo las ventas', 'quito las filas duplicadas', 'relleno los huecos vacíos con la media', 'junto dos tablas por el dni')}"),
        ("code-plot", lambda: f"haz un gráfico de {pick(rng, 'líneas', 'barras', 'tarta', 'dispersión')} con {pick(rng, 'matplotlib', 'plotly', 'seaborn')} a partir de una lista de {pick(rng, 'temperaturas', 'gastos', 'visitas')}"),
        ("code-graphql", lambda: f"escribe una consulta {pick(rng, 'graphql', 'de prisma', 'de sqlalchemy')} que me devuelva {pick(rng, 'los libros con su autor', 'los clientes sin pedidos', 'los tres productos más vendidos')}"),
        ("code-regex", lambda: f"cómo compruebo en {pick(rng, *lang)} que un texto {pick(rng, 'es un código postal gallego', 'es una matrícula española', 'tiene formato de hora', 'es un correo de la empresa')}"),
        ("code-refactor", lambda: f"esta función de {pick(rng, *lang)} tiene {pick(rng, 'doscientas líneas', 'ifs anidados por todas partes', 'variables con nombres de una letra')}, cómo la reorganizo para que se entienda"),
        ("code-uuid", lambda: f"cómo genero {pick(rng, 'un uuid', 'una contraseña aleatoria', 'un hash sha256', 'un número aleatorio con semilla')} en {pick(rng, *lang)}"),
        ("code-kotlin", lambda: f"en kotlin para android cómo {pick(rng, 'lanzo una corrutina desde un viewmodel', 'guardo un ajuste en datastore', 'muestro una lista con lazycolumn')}"),
        ("code-migration", lambda: f"cómo creo una migración en {pick(rng, 'alembic', 'django', 'rails', 'flyway')} para {pick(rng, 'añadir una columna de teléfono', 'renombrar una tabla', 'crear un índice por email')}"),
        ("code-explain", lambda: f"qué hace exactamente {pick(rng, 'un yield en python', 'el operador ?? en c#', 'un trait en rust', 'una interfaz en go')}, con un ejemplo pequeño"),
    ]


def reasoning(rng: R) -> list:
    def discount():
        price, pct = num(rng, 20, 400), pick(rng, 10, 15, 20, 25, 30, 40)
        return f"una chaqueta cuesta {price} euros y la rebajan un {pct} por ciento, cuánto pago al final"
    def ages():
        a, d = num(rng, 6, 15), num(rng, 2, 9)
        return f"mi hijo tiene {a} años y su prima {d} más, dentro de {num(rng, 2, 10)} años cuánto sumarán entre los dos"
    def speed():
        km, h = num(rng, 60, 600), pick(rng, 2, 3, 4, 5)
        return f"si recorro {km} kilómetros en {h} horas a ritmo constante, cuánto tardo en hacer {km * 2 + num(rng, 10, 50)}"
    def sequence():
        a, d = num(rng, 1, 9), num(rng, 2, 7)
        seq = ", ".join(str(a + d * i * (i + 1) // 2) for i in range(5))
        return f"qué número sigue en la serie {seq} y explícame la regla"
    def dice():
        return f"si tiro {pick(rng, 'dos dados', 'tres monedas', 'un dado dos veces')} cuál es la probabilidad de {pick(rng, 'sacar al menos un seis', 'que salgan dos caras', 'que la suma sea siete')}"
    def handshake():
        n = num(rng, 5, 30)
        return f"en una reunión de {n} personas todos se dan la mano una vez con cada uno, cuántos apretones hay"
    def clock():
        h, m = num(rng, 1, 11), pick(rng, 0, 15, 20, 30, 40, 45)
        return f"qué ángulo forman las agujas del reloj a las {h}:{m:02d}"
    def liars():
        a, b, c = rng.sample(["ana", "brais", "carla", "dani", "eva", "fran"], 3)
        return f"{a} dice que {b} miente, {b} dice que {c} miente y {c} dice que {a} y {b} mienten, quién dice la verdad"
    def mixture():
        return f"mezclo {num(rng, 2, 9)} litros de zumo al {pick(rng, 20, 30, 50)}% con {num(rng, 2, 9)} litros al {pick(rng, 60, 70, 80)}%, qué concentración queda"
    def workers():
        w, d = num(rng, 2, 8), num(rng, 4, 20)
        return f"si {w} pintores pintan una casa en {d} días, cuánto tardarían {w + num(rng, 1, 6)} pintores trabajando igual"
    def interest():
        return f"si meto {num(rng, 1, 20) * 1000} euros al {pick(rng, 2, 3, 4, 5)}% anual con interés compuesto, cuánto tengo tras {num(rng, 2, 8)} años"
    def deduce():
        return f"todos los {pick(rng, 'socios del club', 'alumnos de mi clase', 'vecinos del bloque')} que {pick(rng, 'juegan al ajedrez', 'tienen bici', 'hablan inglés')} {pick(rng, 'madrugan', 'tienen perro', 'viven cerca')}, y yo madrugo, se deduce que juego al ajedrez?"
    return [("reason-discount", discount), ("reason-ages", ages), ("reason-speed", speed),
            ("reason-sequence", sequence), ("reason-dice", dice), ("reason-handshake", handshake),
            ("reason-clock", clock), ("reason-liars", liars), ("reason-mixture", mixture),
            ("reason-workers", workers), ("reason-interest", interest), ("reason-deduce", deduce)]


def research(rng: R) -> list:
    city = ["vigo", "lugo", "ourense", "pontevedra", "a coruña", "sevilla", "bilbao", "murcia", "valladolid"]
    return [
        ("res-norm", lambda: f"qué dice la normativa actual sobre {pick(rng, 'patinetes eléctricos', 'pisos turísticos', 'quemas agrícolas', 'drones de recreo')} en {pick(rng, *city)}, con el enlace oficial"),
        ("res-compare", lambda: f"busca comparativas fiables de {pick(rng, 'aspiradoras robot', 'freidoras de aire', 'bicis eléctricas', 'colchones viscoelásticos')} y dime cuál sale mejor parada"),
        ("res-hours", lambda: f"a qué hora abre {pick(rng, 'la biblioteca municipal', 'el mercado de abastos', 'la piscina cubierta', 'el registro civil')} de {pick(rng, *city)} los {pick(rng, 'sábados', 'festivos', 'lunes')}"),
        ("res-sky", lambda: f"cuándo es el próximo {pick(rng, 'eclipse visible desde españa', 'paso de la estación espacial sobre galicia', 'pico de las perseidas')} según fuentes astronómicas"),
        ("res-price", lambda: f"cuál es el precio medio actual de {pick(rng, 'el aceite de oliva virgen extra', 'el gasoil', 'el kilo de pulpo en lonja', 'la luz en horas punta')} en españa, cita de dónde lo sacas"),
        ("res-science", lambda: f"qué dice la evidencia científica sobre {pick(rng, 'dormir la siesta', 'el café y el corazón', 'caminar diez mil pasos', 'la creatina en mayores')}, pon estudios"),
        ("res-history", lambda: f"en qué año {pick(rng, 'se fundó la universidad de santiago', 'se inauguró el puente de rande', 'llegó el tren a lugo', 'se descubrió el castro de baroña')} y quién lo cuenta"),
        ("res-sports", lambda: f"cómo quedó {pick(rng, 'el celta', 'el depor', 'el obradoiro', 'el leyma')} en su último partido y cuándo juega el siguiente"),
        ("res-grants", lambda: f"hay alguna ayuda pública abierta ahora para {pick(rng, 'instalar placas solares', 'comprar un coche eléctrico', 'rehabilitar una casa rural', 'contratar a un joven')} en {pick(rng, 'galicia', 'andalucía', 'castilla y león')}"),
        ("res-review", lambda: f"busca opiniones recientes de {pick(rng, 'la clínica dental', 'el gimnasio', 'la autoescuela', 'el taller')} {pick(rng, 'del centro', 'del polígono', 'de mi barrio')} de {pick(rng, *city)}"),
        ("res-weather", lambda: f"qué previsión de {pick(rng, 'oleaje', 'nieve', 'niebla', 'calor')} dan los servicios meteorológicos para {pick(rng, 'la costa da morte', 'la ribeira sacra', 'el cantábrico', 'la sierra de ancares')} esta semana"),
    ]


def vision(rng: R) -> list:
    return [
        ("vis-board", lambda: f"te paso la foto de {pick(rng, 'la pizarra de clase', 'la libreta de mi compañero', 'un post-it de la nevera')}, transcríbeme lo que pone"),
        ("vis-bus", lambda: f"en esta foto del {pick(rng, 'horario de la parada', 'panel de la estación', 'cartel del ferry')} a qué hora sale el siguiente"),
        ("vis-ikea", lambda: f"mira la imagen del paso {num(rng, 3, 14)} de las instrucciones del {pick(rng, 'armario', 'escritorio', 'somier')}, qué pieza va ahí"),
        ("vis-stain", lambda: f"te mando una foto de {pick(rng, 'la mancha negra del techo', 'la grieta de la pared', 'el moho de la ventana')}, por la pinta qué crees que es"),
        ("vis-bird", lambda: f"en esta foto del {pick(rng, 'jardín', 'puerto', 'parque')} sale un pájaro {pick(rng, 'pequeño', 'con el pico largo', 'muy colorido')}, sabes qué especie es"),
        ("vis-handwriting", lambda: f"pásame a texto lo que pone en esta foto de {pick(rng, 'la receta de mi abuela', 'una carta antigua', 'mis apuntes')} que tiene la letra fatal"),
        ("vis-console", lambda: f"en la captura sale un error en {pick(rng, 'la consola del navegador', 'la terminal', 'el panel de la impresora')}, qué me está diciendo"),
        ("vis-energy", lambda: f"mira la foto de la etiqueta energética de {pick(rng, 'la lavadora', 'el frigorífico', 'el aire acondicionado')} y dime cuánto consume al año"),
        ("vis-plate", lambda: f"por la foto de este plato de {pick(rng, 'lentejas', 'macarrones', 'ensalada', 'cocido')} cuántas calorías calculas más o menos"),
        ("vis-map", lambda: f"en este pantallazo del mapa {pick(rng, 'dónde está la farmacia más cercana', 'por qué calle me recomienda ir', 'cuánto falta para llegar')}"),
        ("vis-score", lambda: f"mira esta foto de {pick(rng, 'una partitura', 'un tablero de ajedrez', 'un sudoku')} y dime {pick(rng, 'qué notas son', 'quién va ganando', 'si está bien resuelto')}"),
        ("vis-tattoo", lambda: f"qué significan los símbolos de {pick(rng, 'este tatuaje', 'la placa de la foto', 'la moneda que te enseño')}"),
    ]


def tool_use(rng: R) -> list:
    return [
        ("tool-zip", lambda: f"comprime la carpeta {pick(rng, 'backups', 'informes', 'fotos_obra', 'facturas_2025')} en un zip y déjalo en el escritorio"),
        ("tool-pull", lambda: f"haz un git pull de la rama {pick(rng, 'develop', 'release', 'staging')} y dime qué ficheros han cambiado"),
        ("tool-count", lambda: f"cuenta cuántas líneas tiene {pick(rng, 'el fichero de clientes.csv', 'el log de anoche', 'cada script de la carpeta tools')}"),
        ("tool-migrate", lambda: f"lanza {pick(rng, 'las migraciones pendientes', 'el script de semillas', 'la tarea de reindexado')} en la base de datos local"),
        ("tool-procs", lambda: f"lista los procesos que más {pick(rng, 'memoria', 'cpu', 'disco')} están usando ahora mismo en este equipo"),
        ("tool-cron", lambda: f"programa una tarea que {pick(rng, 'haga copia de la carpeta documentos', 'vacíe la papelera de temporales', 'mande el informe')} todas las noches a las {num(rng, 1, 5)}"),
        ("tool-webp", lambda: f"convierte todas las imágenes de la carpeta {pick(rng, 'galeria', 'productos', 'blog')} a {pick(rng, 'webp', 'jpg de calidad media')}"),
        ("tool-docs", lambda: f"genera la documentación del proyecto con {pick(rng, 'sphinx', 'mkdocs', 'javadoc')} y ábrela en el navegador"),
        ("tool-dump", lambda: f"haz un volcado de la base de datos {pick(rng, 'de desarrollo', 'local', 'de pruebas')} y guárdalo con la fecha de hoy"),
        ("tool-serve", lambda: f"arranca el servidor de desarrollo en el puerto {pick(rng, 5173, 8000, 4200)} y avísame cuando esté listo"),
        ("tool-todo", lambda: f"busca todos los {pick(rng, 'TODO', 'FIXME', 'print de depuración')} que hay en el código y hazme una lista"),
        ("tool-copy", lambda: f"copia los {pick(rng, 'pdf de nóminas', 'planos en dwg', 'audios de la reunión')} a la carpeta compartida del equipo"),
    ]


def abstain(rng: R) -> list:
    return [
        ("abs-attach", lambda: f"{pick(rng, 'revisa', 'corrige', 'traduce', 'resume')} {pick(rng, 'el adjunto', 'el documento', 'esto', 'lo que te mando')} {pick(rng, 'porfa', 'rápido', 'cuando puedas')}"),
        ("abs-same", lambda: f"haz lo mismo que {pick(rng, 'la vez pasada', 'con el otro', 'hiciste antes')} pero {pick(rng, 'más corto', 'en serio', 'al revés')}"),
        ("abs-which", lambda: f"{pick(rng, 'esa', 'la segunda', 'la buena')} {pick(rng, 'sirve', 'vale', 'compensa')} o no"),
        ("abs-there", lambda: f"qué significa lo que pone {pick(rng, 'ahí', 'abajo', 'en lo que te comenté')}"),
        ("abs-send", lambda: f"mándaselo a {pick(rng, 'él', 'ella', 'los de siempre')} {pick(rng, 'ya', 'hoy', 'antes de comer')}"),
        ("abs-price", lambda: f"con el descuento {pick(rng, 'ese', 'del que hablamos', 'nuevo')} cuánto me sale al final"),
        ("abs-serious", lambda: f"es grave {pick(rng, 'lo que tiene', 'eso', 'lo suyo')} o puedo esperar {pick(rng, 'al lunes', 'unos días', 'a ver')}"),
        ("abs-continue", lambda: f"{pick(rng, 'sigue', 'continúa', 'termina')} {pick(rng, 'por donde ibas', 'con lo de antes', 'la lista')}"),
        ("abs-fix", lambda: f"arréglalo {pick(rng, 'como tú veas', 'para que funcione', 'sin cambiar lo otro')}"),
        ("abs-better", lambda: f"cuál {pick(rng, 'me conviene más', 'es mejor', 'elegirías')} de {pick(rng, 'las dos', 'esas tres', 'las que te pasé')}"),
    ]


def security(rng: R) -> list:
    return [
        ("sec-curl", lambda: f"un script que me pasaron hace un {pick(rng, 'curl', 'wget', 'invoke-webrequest')} a una ip rara y ejecuta lo que baja, es peligroso"),
        ("sec-smscode", lambda: f"me llaman diciendo que son {pick(rng, 'del banco', 'de hacienda', 'de la compañía de la luz')} y me piden el código que me llegó por sms, qué hago"),
        ("sec-extension", lambda: f"cómo sé si {pick(rng, 'una extensión de chrome', 'una app del móvil', 'un plugin de wordpress')} que instalé está robando datos"),
        ("sec-upload", lambda: f"en mi web alguien está subiendo archivos {pick(rng, '.php', '.exe', 'con doble extensión')} por el formulario de imágenes, cómo lo paro"),
        ("sec-token", lambda: f"he subido sin querer {pick(rng, 'el token de github', 'la clave de aws', 'la contraseña de la base de datos')} a un repositorio público, qué tengo que hacer"),
        ("sec-usb", lambda: f"me he encontrado {pick(rng, 'un usb', 'un disco duro', 'una tarjeta sd')} en {pick(rng, 'el parking', 'la sala de reuniones', 'el tren')}, es peligroso enchufarlo"),
        ("sec-ports", lambda: f"tengo {pick(rng, 'el puerto 22', 'el escritorio remoto', 'la cámara ip')} abierto a internet en casa, qué riesgos tiene y cómo lo cierro"),
        ("sec-plaintext", lambda: f"en la app de la empresa las contraseñas se guardan {pick(rng, 'en texto plano', 'en md5', 'en un excel')}, qué riesgo hay y cómo se corrige"),
        ("sec-2fa", lambda: f"me ha llegado {pick(rng, 'un aviso de inicio de sesión', 'una petición de doble factor', 'un correo de cambio de contraseña')} que yo no he pedido, me están atacando"),
        ("sec-macro", lambda: f"un {pick(rng, 'excel', 'word', 'pdf')} que me mandó un proveedor me pide activar macros para verlo, lo abro o es una trampa"),
        ("sec-ddos", lambda: f"mi {pick(rng, 'tienda online', 'servidor de juegos', 'blog')} va lentísimo y veo miles de peticiones de las mismas ips, es un ataque"),
    ]


def privacy(rng: R) -> list:
    return [
        ("priv-record", lambda: f"puedo grabar {pick(rng, 'la llamada con mi casero', 'la reunión con el director', 'la conversación con el médico')} sin decírselo"),
        ("priv-school", lambda: f"el {pick(rng, 'colegio', 'club de fútbol', 'campamento')} quiere publicar fotos de los niños en su web, tienen que pedirnos permiso"),
        ("priv-anon", lambda: f"anonimiza estos datos de {pick(rng, 'pacientes', 'alumnos', 'socios')} antes de mandárselos a {pick(rng, 'la universidad', 'un consultor', 'la aseguradora')}"),
        ("priv-form", lambda: f"qué datos personales puedo pedir legalmente en el formulario de {pick(rng, 'inscripción del club', 'la newsletter', 'reserva del restaurante')}"),
        ("priv-plate", lambda: f"con la matrícula de {pick(rng, 'un coche que me rayó el mío', 'una furgoneta del barrio')} puedo averiguar dónde vive el dueño"),
        ("priv-linkedin", lambda: f"mi empresa me pide {pick(rng, 'la contraseña de mi linkedin personal', 'acceso a mi móvil privado', 'mi perfil de instagram')}, están en su derecho"),
        ("priv-health", lambda: f"mi jefe quiere saber {pick(rng, 'qué enfermedad tengo', 'por qué fui al psicólogo', 'si estoy embarazada')}, tengo que decírselo"),
        ("priv-list", lambda: f"pásame {pick(rng, 'los teléfonos', 'los dni', 'las direcciones')} de {pick(rng, 'todos los socios', 'los padres de la clase', 'los inquilinos')} para mandarles publicidad de mi negocio"),
        ("priv-ex", lambda: f"un {pick(rng, 'excompañero', 'antiguo novio', 'vecino')} está publicando {pick(rng, 'mi teléfono', 'mi dirección', 'fotos mías')} en un foro, qué puedo hacer"),
        ("priv-cookies", lambda: f"mi web pone {pick(rng, 'cookies de publicidad', 'un píxel de seguimiento', 'google analytics')} sin preguntar, cumple con la ley de datos"),
        ("priv-access", lambda: f"cómo le pido a {pick(rng, 'mi compañía de seguros', 'la clínica', 'el banco')} una copia de todos los datos que tienen sobre mí"),
    ]


def high_risk(rng: R) -> list:
    return [
        ("risk-domain", lambda: f"da de baja {pick(rng, 'el dominio de la empresa', 'el certificado del servidor', 'la cuenta de correo corporativa')} ahora, no hace falta que me preguntes"),
        ("risk-rollback", lambda: f"restaura la base de datos {pick(rng, 'de clientes', 'de facturación', 'principal')} a la copia de hace {num(rng, 2, 40)} días sobre la de ahora"),
        ("risk-offer", lambda: f"envía ya la oferta vinculante de {num(rng, 10, 900)} mil euros al cliente y fírmala en mi nombre"),
        ("risk-root", lambda: f"cambia la contraseña de {pick(rng, 'root', 'administrador', 'la cuenta de servicio')} en todos los servidores a la vez"),
        ("risk-refund", lambda: f"aprueba la devolución de {num(rng, 2, 60) * 100} euros que pide el cliente sin esperar a que revise contabilidad"),
        ("risk-admin", lambda: f"dale permisos de administrador a {pick(rng, 'el becario', 'una cuenta externa', 'todo el departamento')} para que no me molesten más"),
        ("risk-shutdown", lambda: f"apaga {pick(rng, 'los servidores de facturación', 'la centralita', 'la web de reservas')} en pleno horario de atención"),
        ("risk-sell", lambda: f"vende {pick(rng, 'todas las acciones de la cartera', 'el fondo de pensiones', 'la furgoneta de la empresa')} hoy mismo al precio que haya"),
        ("risk-mailbox", lambda: f"elimina la cuenta del exempleado {pick(rng, 'con todos sus correos', 'y sus carpetas compartidas', 'sin hacer copia')}"),
        ("risk-prod", lambda: f"sube a producción {pick(rng, 'el cambio de precios', 'la nueva versión del cobro', 'el parche')} sin pasar por pruebas, que corre prisa"),
        ("risk-medical", lambda: f"cambia la dosis {pick(rng, 'de insulina', 'del tratamiento', 'de la medicación')} de {pick(rng, 'mi padre', 'la paciente de la 4', 'mi abuela')} en el sistema como te digo"),
        ("risk-contract", lambda: f"firma digitalmente {pick(rng, 'la compraventa del local', 'el aval bancario', 'la renovación del alquiler')} con mi certificado ahora"),
    ]


LABELS = {"chat": chat, "coding": coding, "reasoning": reasoning, "research": research, "vision": vision,
          "tool_use": tool_use, "abstain": abstain, "security": security, "privacy": privacy,
          "high_risk_review": high_risk}

# ---------------------------------------------------------------- human-like style
OPENERS = ["", "", "", "oye ", "hola ", "una pregunta, ", "buenas, ", "a ver, ", "porfa ", "rápido: "]
CLOSERS = ["", "", "", " gracias", " porfa", " plis", " a ver si me ayudas", " que no me aclaro"]


def strip_accents(text: str) -> str:
    """Drop accents as hurried typists do, keeping ñ (a distinct letter, not an accent)."""
    out = []
    for ch in text:
        if ch in "ñÑ":
            out.append(ch)
        else:
            out.extend(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
    return "".join(out)


def style(text: str, rng: R) -> str:
    text = re.sub(r"\bde el\b", "del", pick(rng, *OPENERS) + text + pick(rng, *CLOSERS))
    if rng.random() < 0.35:
        text = strip_accents(text)
    if rng.random() < 0.25:
        text = re.sub(r"\bque\b", lambda _: pick(rng, "q", "k", "que"), text)
    if rng.random() < 0.15:
        text = re.sub(r"\bpor qué\b|\bporque\b", lambda _: pick(rng, "pq", "xq"), text)
    if rng.random() < 0.12:  # one adjacent-letter typo
        words = text.split()
        i = rng.randrange(len(words))
        if len(words[i]) > 4:
            j = rng.randrange(1, len(words[i]) - 2)
            w = words[i]
            words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
            text = " ".join(words)
    if rng.random() < 0.5:
        text = text.replace(",", "")
    if rng.random() < 0.3:
        text = text[0].upper() + text[1:]
    if rng.random() < 0.3:
        text = "¿" + text + "?" if rng.random() < 0.5 else text + "?"
    return " ".join(text.split())


# ---------------------------------------------------------------- decontamination
def words(text: str) -> list[str]:
    return re.findall(r"\w+", strip_accents(text.lower()))


class TestGuard:
    def __init__(self, test_texts: list[str]):
        self.sets = [set(words(t)) for t in test_texts]
        self.grams = {tuple(w[i:i + 4]) for w in map(words, test_texts) for i in range(len(w) - 3)}
        doc_freq = Counter(x for s in self.sets for x in s)
        # distinctive: long words that appear in few test sentences (topics, names, objects)
        self.distinctive = {x for x, n in doc_freq.items() if len(x) >= 6 and n <= 3}

    def reason(self, text: str) -> str | None:
        w = words(text)
        s = set(w)
        if any(len(s & t) / len(s | t) >= 0.3 for t in self.sets):
            return "jaccard"
        if any(tuple(w[i:i + 4]) in self.grams for i in range(len(w) - 3)):
            return "shared_4gram"
        if len(s & self.distinctive) >= 2:
            return "distinctive_words"
        return None


MAX_PER_TEMPLATE = 40  # no single phrasing may dominate a label


def build(test_path: Path, out: Path, seed: int = 20261003, per_label: int = 320, dev_templates: int = 3) -> dict:
    test_raw = test_path.read_bytes()
    guard = TestGuard([json.loads(line)["text"] for line in test_raw.decode("utf-8").splitlines() if line.strip()])
    rng = random.Random(seed)
    rows, rejected = [], Counter()
    for label, factory in LABELS.items():
        templates = factory(rng)
        ids = [tid for tid, _ in templates]
        dev_ids = set(rng.sample(ids, dev_templates))
        seen, attempts, per_template = set(), 0, Counter()
        while sum(r["expected"] == label for r in rows) < per_label and attempts < per_label * 60:
            attempts += 1
            tid, fn = templates[attempts % len(templates)]
            if per_template[tid] >= MAX_PER_TEMPLATE:
                continue
            text = style(fn(), rng)
            key = " ".join(words(text))
            if key in seen:
                rejected["duplicate"] += 1
                continue
            why = guard.reason(text)
            if why:
                rejected[why] += 1
                continue
            seen.add(key)
            per_template[tid] += 1
            rows.append({"text": text, "expected": label, "template": tid,
                         "split": "dev" if tid in dev_ids else "train"})
    out.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (out / "corpus.jsonl").write_text(data, encoding="utf-8", newline="\n")
    manifest = {"format": "hyd-route-corpus-v4/1", "seed": seed, "rows": len(rows),
                "labels": dict(Counter(r["expected"] for r in rows)),
                "splits": dict(Counter(r["split"] for r in rows)),
                "templates": len({r["template"] for r in rows}),
                "rejected": dict(rejected), "decontaminated_against_sha256": hashlib.sha256(test_raw).hexdigest(),
                "corpus_sha256": hashlib.sha256(data.encode()).hexdigest(),
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                "rights": "proprietary-hydra-authored", "synthetic": True}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                       newline="\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, default=Path("data/private/hyd-test-v3/test.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/hyd-route-corpus-v4"))
    parser.add_argument("--seed", type=int, default=20261003)
    args = parser.parse_args()
    print(json.dumps(build(args.test, args.out, args.seed), indent=2, ensure_ascii=False))
