package com.sebasarchive.kardex.ui.pantallas

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.auth.AuthRepository
import com.sebasarchive.kardex.auth.Claves
import com.sebasarchive.kardex.ui.Textos
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.theme.Marca
import kotlin.math.hypot

enum class ModoAuth { ENTRAR, REGISTRO, RECUPERAR }

data class AuthUi(
    val modo: ModoAuth = ModoAuth.ENTRAR,
    val cargando: Boolean = false,
    val error: String? = null,
    /** Mensaje de buena noticia (p. ej. «Contraseña cambiada»). */
    val aviso: String? = null,
    /** Recuperar: la pregunta de seguridad de la cuenta encontrada (paso 2), o null (paso 1). */
    val pregunta: String? = null,
    /** Cambia con cada error: la tarjeta se sacude. */
    val sacudida: Int = 0,
    /** Nombre de quien acaba de entrar: dispara la animación de bienvenida. */
    val bienvenida: String? = null,
)

data class DatosRegistro(
    val nombre: String = "", val usuario: String = "", val correo: String = "", val clave: String = "",
    val confirmacion: String = "", val pregunta: String = AuthRepository.PREGUNTAS.first(), val respuesta: String = "",
)

/**
 * Acceso a la app: entrar, crear cuenta y recuperar la contraseña, en una sola pantalla que cambia de formulario
 * con una transición lateral. Las cuentas son locales (la app trabaja sin red).
 */
@Composable
fun AuthScreen(
    ui: AuthUi,
    alCambiarModo: (ModoAuth) -> Unit,
    alEntrar: (usuario: String, clave: String) -> Unit,
    alRegistrar: (DatosRegistro) -> Unit,
    alBuscarPregunta: (usuario: String) -> Unit,
    alRestablecer: (usuario: String, respuesta: String, clave: String, confirmacion: String) -> Unit,
    inicial: DatosRegistro = DatosRegistro(),
) {
    var datos by rememberSaveable(stateSaver = androidx.compose.runtime.saveable.listSaver<DatosRegistro, String>(
        save = { listOf(it.nombre, it.usuario, it.correo, it.clave, it.confirmacion, it.pregunta, it.respuesta) },
        restore = { DatosRegistro(it[0], it[1], it[2], it[3], it[4], it[5], it[6]) },
    )) { mutableStateOf(inicial) }
    BackHandler(enabled = ui.modo != ModoAuth.ENTRAR && ui.bienvenida == null) { alCambiarModo(ModoAuth.ENTRAR) }

    val sacudida = remember { Animatable(0f) }
    LaunchedEffect(ui.sacudida) {
        if (ui.sacudida > 0) for (x in listOf(-16f, 13f, -9f, 6f, -3f, 0f)) sacudida.animateTo(x, tween(55))
    }
    val llegada = remember { MutableTransitionState(false).apply { targetState = true } }

    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Cabecera()
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            AnimatedVisibility(llegada, enter = scaleIn(spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)) + fadeIn()) {
                Box(Modifier.size(84.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f)), contentAlignment = Alignment.Center) {
                    Icon(Iconos.Caja, contentDescription = null, tint = Color.White, modifier = Modifier.size(44.dp))
                }
            }
            Spacer(Modifier.height(12.dp))
            Text(Textos.t("Inventario"), color = Color.White, style = MaterialTheme.typography.headlineSmall)
            AnimatedContent(ui.modo, transitionSpec = { fadeIn(tween(250)).togetherWith(fadeOut(tween(150))) }, label = "subtitulo") { modo ->
                Text(
                    when (modo) {
                        ModoAuth.ENTRAR -> Textos.t("Entra para empezar a contar")
                        ModoAuth.REGISTRO -> Textos.t("Crea tu cuenta en este teléfono")
                        ModoAuth.RECUPERAR -> Textos.t("Recupera tu contraseña")
                    },
                    color = Color.White.copy(alpha = 0.85f), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.height(22.dp))
            AnimatedVisibility(llegada, enter = slideInVertically(tween(520, delayMillis = 120, easing = FastOutSlowInEasing)) { it / 2 } + fadeIn(tween(400, delayMillis = 120))) {
                Surface(
                    shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surface, shadowElevation = 10.dp,
                    modifier = Modifier.fillMaxWidth().graphicsLayer { translationX = sacudida.value.dp.toPx() },
                ) {
                    // Cada formulario entra por el lado hacia el que se avanza, creciendo; el anterior se aleja.
                    AnimatedContent(
                        targetState = ui.modo,
                        transitionSpec = {
                            val adelante = targetState.ordinal > initialState.ordinal
                            (slideInHorizontally(tween(420, easing = FastOutSlowInEasing)) { if (adelante) it else -it } +
                                fadeIn(tween(320)) + scaleIn(tween(420, easing = FastOutSlowInEasing), initialScale = 0.88f))
                                .togetherWith(slideOutHorizontally(tween(320)) { if (adelante) -it / 2 else it / 2 } +
                                    fadeOut(tween(200)) + scaleOut(tween(320), targetScale = 0.88f))
                                .using(SizeTransform(clip = false))
                        },
                        label = "formulario",
                    ) { modo ->
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Mensajes(ui)
                            when (modo) {
                                ModoAuth.ENTRAR -> FormularioEntrar(ui, datos, { datos = it }, alEntrar, alCambiarModo)
                                ModoAuth.REGISTRO -> FormularioRegistro(ui, datos, { datos = it }, alRegistrar, alCambiarModo)
                                ModoAuth.RECUPERAR -> FormularioRecuperar(ui, datos, { datos = it }, alBuscarPregunta, alRestablecer, alCambiarModo)
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Text(Textos.t("Las cuentas se guardan en este teléfono: la app funciona sin red."), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        }
        Bienvenida(ui.bienvenida)
    }
}

/** Franja superior con el degradado de la marca y tres discos que flotan despacio. */
@Composable
private fun Cabecera() {
    val t by rememberInfiniteTransition(label = "fondo").animateFloat(
        0f, 1f, infiniteRepeatable(tween(7000, easing = LinearEasing), RepeatMode.Reverse), label = "t")
    Box(
        Modifier.fillMaxWidth().height(330.dp).clip(RoundedCornerShape(bottomStart = 40.dp, bottomEnd = 40.dp))
            .background(Brush.linearGradient(listOf(Marca.Verde, Marca.VerdeProfundo)))
    ) {
        Box(Modifier.size(220.dp).align(Alignment.TopEnd).offset(x = (70 - 30 * t).dp, y = (-80 + 24 * t).dp).clip(CircleShape).background(Color.White.copy(alpha = 0.08f)))
        Box(Modifier.size(150.dp).align(Alignment.BottomStart).offset(x = (-50 + 36 * t).dp, y = (30 - 20 * t).dp).clip(CircleShape).background(Color.White.copy(alpha = 0.07f)))
        Box(Modifier.size(70.dp).align(Alignment.CenterEnd).offset(x = (-30 - 20 * t).dp, y = (40 * t).dp).clip(CircleShape).background(Color.White.copy(alpha = 0.06f)))
    }
}

@Composable
private fun Mensajes(ui: AuthUi) {
    AnimatedVisibility(ui.error != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
        Franja(Icons.Default.Warning, ui.error.orEmpty(), MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.error, MaterialTheme.colorScheme.onErrorContainer)
    }
    AnimatedVisibility(ui.aviso != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
        Franja(Icons.Default.CheckCircle, ui.aviso.orEmpty(), MaterialTheme.colorScheme.primaryContainer, MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.onPrimaryContainer)
    }
}

@Composable
private fun Franja(icono: ImageVector, texto: String, fondo: Color, tinte: Color, colorTexto: Color) {
    Surface(color = fondo, shape = MaterialTheme.shapes.medium) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icono, contentDescription = null, tint = tinte)
            Spacer(Modifier.width(10.dp))
            Text(texto, style = MaterialTheme.typography.bodyMedium, color = colorTexto)
        }
    }
}

@Composable
private fun CampoUsuario(valor: String, alCambiar: (String) -> Unit, ayuda: String? = null) {
    OutlinedTextField(
        value = valor, onValueChange = { if (it.length <= 24) alCambiar(it.replace(" ", "").replace("\n", "")) },
        label = { Text(Textos.t("Usuario")) }, singleLine = true,
        leadingIcon = { Icon(Icons.Default.Person, contentDescription = null) },
        supportingText = ayuda?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun CampoClave(valor: String, alCambiar: (String) -> Unit, etiqueta: String, esError: Boolean = false, accion: ImeAction = ImeAction.Next) {
    var visible by rememberSaveable { mutableStateOf(false) }
    OutlinedTextField(
        value = valor, onValueChange = { if (it.length <= 64) alCambiar(it.replace("\n", "")) },
        label = { Text(etiqueta) }, singleLine = true, isError = esError,
        leadingIcon = { Icon(Icons.Default.Lock, contentDescription = null) },
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(Iconos.Ojo, contentDescription = Textos.t(if (visible) "Ocultar contraseña" else "Mostrar contraseña"),
                    tint = if (visible) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = accion),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun BotonPrincipal(texto: String, cargando: Boolean, alPulsar: () -> Unit) {
    Button(onClick = alPulsar, enabled = !cargando, modifier = Modifier.fillMaxWidth().height(54.dp)) {
        AnimatedContent(cargando, transitionSpec = { (fadeIn() + scaleIn()).togetherWith(fadeOut() + scaleOut()) }, label = "boton") { ocupado ->
            if (ocupado) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.5.dp, color = MaterialTheme.colorScheme.onSurface)
            else Text(texto)
        }
    }
}

@Composable
private fun FormularioEntrar(ui: AuthUi, d: DatosRegistro, alCambiar: (DatosRegistro) -> Unit,
                             alEntrar: (String, String) -> Unit, alCambiarModo: (ModoAuth) -> Unit) {
    Text(Textos.t("Iniciar sesión"), style = MaterialTheme.typography.titleLarge)
    CampoUsuario(d.usuario, { alCambiar(d.copy(usuario = it)) })
    CampoClave(d.clave, { alCambiar(d.copy(clave = it)) }, Textos.t("Contraseña"), accion = ImeAction.Done)
    BotonPrincipal(Textos.t("Entrar"), ui.cargando) { alEntrar(d.usuario, d.clave) }
    TextButton(onClick = { alCambiarModo(ModoAuth.RECUPERAR) }, modifier = Modifier.fillMaxWidth()) { Text(Textos.t("¿Olvidaste tu contraseña?")) }
    OutlinedButton(onClick = { alCambiarModo(ModoAuth.REGISTRO) }, modifier = Modifier.fillMaxWidth().height(50.dp)) { Text(Textos.t("Crear cuenta")) }
}

@Composable
private fun FormularioRegistro(ui: AuthUi, d: DatosRegistro, alCambiar: (DatosRegistro) -> Unit,
                               alRegistrar: (DatosRegistro) -> Unit, alCambiarModo: (ModoAuth) -> Unit) {
    Text(Textos.t("Crear cuenta"), style = MaterialTheme.typography.titleLarge)
    OutlinedTextField(
        value = d.nombre, onValueChange = { if (it.length <= 70) alCambiar(d.copy(nombre = it.replace("\n", ""))) },
        label = { Text(Textos.t("Nombre completo")) }, singleLine = true,
        supportingText = { Text(Textos.t("Aparece como operador en cada lectura")) },
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
    CampoUsuario(d.usuario, { alCambiar(d.copy(usuario = it)) }, ayuda = Textos.t("3 a 20: letras, números, punto o guion"))
    OutlinedTextField(
        value = d.correo, onValueChange = { if (it.length <= 120) alCambiar(d.copy(correo = it.trim())) },
        label = { Text(Textos.t("Correo (opcional)")) }, singleLine = true,
        supportingText = { Text(Textos.t("No se usa para entrar; es un dato de perfil")) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
    CampoClave(d.clave, { alCambiar(d.copy(clave = it)) }, Textos.t("Contraseña"))
    BarraFuerza(d.clave)
    CampoClave(d.confirmacion, { alCambiar(d.copy(confirmacion = it)) }, Textos.t("Repite la contraseña"),
        esError = d.confirmacion.isNotEmpty() && d.confirmacion != d.clave)

    Text(
        Textos.t("Tu cuenta quedará pendiente hasta que el administrador la apruebe en el PC. Se entera al sincronizar."),
        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    SelectorPregunta(d.pregunta) { alCambiar(d.copy(pregunta = it)) }
    OutlinedTextField(
        value = d.respuesta, onValueChange = { if (it.length <= 60) alCambiar(d.copy(respuesta = it.replace("\n", ""))) },
        label = { Text(Textos.t("Tu respuesta")) }, singleLine = true,
        supportingText = { Text(Textos.t("Sirve para recuperar la contraseña sin internet")) },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), modifier = Modifier.fillMaxWidth(),
    )
    BotonPrincipal(Textos.t("Crear cuenta"), ui.cargando) { alRegistrar(d) }
    TextButton(onClick = { alCambiarModo(ModoAuth.ENTRAR) }, modifier = Modifier.fillMaxWidth()) { Text(Textos.t("Ya tengo cuenta")) }
}

@Composable
private fun FormularioRecuperar(ui: AuthUi, d: DatosRegistro, alCambiar: (DatosRegistro) -> Unit, alBuscarPregunta: (String) -> Unit,
                                alRestablecer: (String, String, String, String) -> Unit, alCambiarModo: (ModoAuth) -> Unit) {
    Text(Textos.t("Recuperar contraseña"), style = MaterialTheme.typography.titleLarge)
    Text(Textos.t("Responde la pregunta de seguridad que elegiste al crear la cuenta."), style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
    CampoUsuario(d.usuario, { alCambiar(d.copy(usuario = it)) })
    AnimatedVisibility(ui.pregunta != null, enter = expandVertically(tween(380)) + fadeIn(tween(380)), exit = shrinkVertically() + fadeOut()) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Surface(color = MaterialTheme.colorScheme.tertiaryContainer, shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(Textos.t("Tu pregunta"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
                    Text(Textos.t(ui.pregunta.orEmpty()), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
                }
            }
            OutlinedTextField(
                value = d.respuesta, onValueChange = { if (it.length <= 60) alCambiar(d.copy(respuesta = it.replace("\n", ""))) },
                label = { Text(Textos.t("Tu respuesta")) }, singleLine = true, keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            CampoClave(d.clave, { alCambiar(d.copy(clave = it)) }, Textos.t("Contraseña nueva"))
            BarraFuerza(d.clave)
            CampoClave(d.confirmacion, { alCambiar(d.copy(confirmacion = it)) }, Textos.t("Repite la contraseña nueva"),
                esError = d.confirmacion.isNotEmpty() && d.confirmacion != d.clave, accion = ImeAction.Done)
        }
    }
    if (ui.pregunta == null) BotonPrincipal(Textos.t("Buscar mi pregunta"), ui.cargando) { alBuscarPregunta(d.usuario) }
    else BotonPrincipal(Textos.t("Cambiar contraseña"), ui.cargando) { alRestablecer(d.usuario, d.respuesta, d.clave, d.confirmacion) }
    TextButton(onClick = { alCambiarModo(ModoAuth.ENTRAR) }, modifier = Modifier.fillMaxWidth()) { Text(Textos.t("Volver a entrar")) }
}

/** Cuatro tramos que se llenan y cambian de color según la fuerza de la contraseña. */
@Composable
fun BarraFuerza(clave: String) {
    val fuerza = Claves.fuerza(clave)
    val color by animateColorAsState(
        when {
            clave.isEmpty() -> MaterialTheme.colorScheme.outlineVariant
            !Claves.esAceptable(clave) -> MaterialTheme.colorScheme.error
            fuerza <= 2 -> Marca.Pendiente
            else -> Marca.Confirmado
        }, label = "color")
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            repeat(4) { i ->
                val lleno by animateFloatAsState(if (i < fuerza) 1f else 0f, tween(260), label = "tramo")
                Box(Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.surfaceVariant)) {
                    Box(Modifier.fillMaxWidth(lleno).height(6.dp).background(color))
                }
            }
        }
        Text(
            when {
                clave.isEmpty() -> Textos.t("Mínimo 8 caracteres, con letras y números")
                !Claves.esAceptable(clave) -> Textos.t("Todavía no: mínimo 8 caracteres, con letras y números")
                fuerza <= 2 -> Textos.t("Aceptable")
                fuerza == 3 -> Textos.t("Buena")
                else -> Textos.t("Fuerte")
            },
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SelectorPregunta(pregunta: String, alElegir: (String) -> Unit) {
    var abierto by remember { mutableStateOf(false) }
    Box {
        OutlinedTextField(
            value = Textos.t(pregunta), onValueChange = {}, readOnly = true, label = { Text(Textos.t("Pregunta de seguridad")) },
            trailingIcon = { Icon(Icons.Default.ArrowDropDown, contentDescription = null) }, modifier = Modifier.fillMaxWidth(),
        )
        Box(Modifier.matchParentSize().clip(MaterialTheme.shapes.small).clickable { abierto = true })  // el campo es de solo lectura: el toque lo recibe esta capa
        DropdownMenu(expanded = abierto, onDismissRequest = { abierto = false }) {
            AuthRepository.PREGUNTAS.forEach { opcion ->
                DropdownMenuItem(text = { Text(Textos.t(opcion)) }, onClick = { alElegir(opcion); abierto = false })
            }
        }
    }
}

/** Al entrar: un círculo verde crece desde el centro hasta cubrir la pantalla, con el saludo. Después se abre el inicio. */
@Composable
private fun Bienvenida(nombre: String?) {
    val escala by animateFloatAsState(if (nombre != null) 1f else 0f, tween(620, easing = FastOutSlowInEasing), label = "revelado")
    if (escala == 0f) return
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) { drawCircle(Marca.Verde, radius = hypot(size.width, size.height) / 2 * escala) }
        AnimatedVisibility(escala > 0.55f, enter = scaleIn(spring(dampingRatio = Spring.DampingRatioMediumBouncy)) + fadeIn()) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Box(Modifier.size(112.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Check, contentDescription = null, tint = Marca.Verde, modifier = Modifier.size(64.dp))
                }
                Text(Textos.t("¡Hola, {nombre}!", "nombre" to nombre.orEmpty().substringBefore(' ')), color = Color.White, style = MaterialTheme.typography.headlineSmall)
            }
        }
    }
}
