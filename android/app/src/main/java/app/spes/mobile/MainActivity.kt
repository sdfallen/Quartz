package app.spes.mobile

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private enum class Tab(val label: String) { Chat("Sohbet"), Team("Ekip"), Work("İş"), List("Sohbetler") }

private val MODES = listOf("collaboration" to "Birlikte", "claude" to "Fatum", "codex" to "Fides", "antigravity" to "Eos")
private val STEP = mapOf(1 to "Plan", 2 to "Eleştiri", 3 to "Karar", 4 to "Hazırlık", 5 to "Kontrol", 6 to "Kapanış")

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifier.ensureChannels(this)
        askNotificationPermission()
        WatchService.start(this)
        setContent { SpesTheme { App() } }
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7)
    }

    private suspend fun <T> io(block: () -> T): Result<T> = withContext(Dispatchers.IO) { runCatching(block) }
    private fun api() = Prefs.api(this)

    @Composable
    private fun App() {
        var paired by remember { mutableStateOf(Prefs.paired(this)) }
        var settings by remember { mutableStateOf(false) }
        Box(Modifier.fillMaxSize().background(SpesColors.bg).safeDrawingPadding()) {
            AnimatedContent(targetState = Triple(paired, settings, 0), transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(160)) }, label = "root") { (p, s, _) ->
                when {
                    !p -> PairScreen { paired = true; WatchService.start(this@MainActivity) }
                    s -> SettingsScreen(onBack = { settings = false }, onForget = {
                        WatchService.stop(this@MainActivity); Prefs.forget(this@MainActivity); settings = false; paired = false
                    })
                    else -> Home(onSettings = { settings = true }, onUnpaired = { paired = false })
                }
            }
        }
    }

    @Composable
    private fun Brand(subtitle: String, big: Boolean = false) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.drawable.ic_launcher_foreground), contentDescription = null, modifier = Modifier.size(if (big) 52.dp else 40.dp))
            Column {
                Text("SpeS", color = SpesColors.text, fontSize = if (big) 22.sp else 19.sp, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = SpesColors.text3, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }

    // -- pairing -----------------------------------------------------------
    @Composable
    private fun PairScreen(onPaired: () -> Unit) {
        val scope = rememberCoroutineScope()
        var url by remember { mutableStateOf(Prefs.url(this)) }
        var code by remember { mutableStateOf("") }
        var busy by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf("") }
        Column(Modifier.fillMaxSize().padding(24.dp).imePadding(), verticalArrangement = Arrangement.Center) {
            Brand("Telefonu bilgisayarındaki SpeS ile eşleştir", big = true)
            Spacer(Modifier.height(28.dp))
            Text("1. Bilgisayarda SpeS → Durum ve araçlar → Araçlar → Mobil erişim'i aç.\n" +
                "2. Tailscale adresini ve 6 haneli eşleştirme kodunu buraya yaz.", color = SpesColors.text2, fontSize = 14.sp, lineHeight = 21.sp)
            Spacer(Modifier.height(20.dp))
            OutlinedTextField(url, { url = it.trim() }, singleLine = true, label = { Text("Tailscale adresi") },
                placeholder = { Text("bilgisayar.tailnet.ts.net") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(code, { code = it.filter(Char::isDigit).take(6) }, singleLine = true, label = { Text("Eşleştirme kodu") },
                placeholder = { Text("6 hane") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth())
            AnimatedVisibility(error.isNotEmpty()) { Text(error, color = SpesColors.danger, fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp)) }
            Spacer(Modifier.height(20.dp))
            Button(enabled = !busy && url.isNotBlank() && code.length == 6, onClick = {
                busy = true; error = ""
                scope.launch {
                    val r = io { val base = SpesApi.normalize(url); base to SpesApi.pair(base, code) }
                    busy = false
                    r.onSuccess { (base, token) -> Prefs.savePairing(this@MainActivity, base, token); onPaired() }
                        .onFailure { error = it.message ?: "Bağlanılamadı" }
                }
            }, modifier = Modifier.fillMaxWidth().height(52.dp)) { Text(if (busy) "Bağlanıyor…" else "Eşleştir") }
        }
    }

    // -- home with tabs ----------------------------------------------------
    @Composable
    private fun Home(onSettings: () -> Unit, onUnpaired: () -> Unit) {
        val scope = rememberCoroutineScope()
        var tab by remember { mutableStateOf(Tab.Chat) }
        var state by remember { mutableStateOf<SpesApi.State?>(null) }
        var overview by remember { mutableStateOf<SpesApi.Overview?>(null) }
        var error by remember { mutableStateOf("") }
        var note by remember { mutableStateOf("") }
        var refresh by remember { mutableIntStateOf(0) }

        LaunchedEffect(refresh) {
            while (true) {
                io { api().state(0, 0) }.onSuccess { state = it; error = "" }.onFailure {
                    if (it is SpesApi.AuthException) { Prefs.forget(this@MainActivity); onUnpaired(); return@LaunchedEffect }
                    error = "Bilgisayara ulaşılamıyor. Tailscale açık ve SpeS çalışıyor mu?"
                }
                delay(if (state?.busy == true) 1_800 else 4_000)
            }
        }
        LaunchedEffect(tab, refresh) {
            while (tab == Tab.Team || tab == Tab.Work) {
                io { api().overview() }.onSuccess { overview = it }
                delay(8_000)
            }
        }
        LaunchedEffect(note) { if (note.isNotEmpty()) { delay(3_000); note = "" } }

        fun act(action: String, body: JSONObject = JSONObject(), done: String = "") {
            scope.launch {
                io { api().act(action, body) }.onSuccess { if (done.isNotEmpty()) note = done; refresh++ }
                    .onFailure { note = it.message ?: "İşlem yapılamadı" }
            }
        }
        fun stop() {
            note = "Durdurma gönderiliyor…"
            scope.launch { note = if (io { api().stop() }.isSuccess) "Durdurma iletildi" else "Durdurma iletilemedi"; refresh++ }
        }

        Column(Modifier.fillMaxSize()) {
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { Brand(state?.title ?: "Bağlanıyor…") }
                TextButton(onClick = onSettings) { Text("Ayarlar", color = SpesColors.text2) }
            }
            StatusBar(state, ::stop)
            AnimatedVisibility(error.isNotEmpty(), enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                Text(error, color = SpesColors.danger, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            }
            AnimatedVisibility(note.isNotEmpty(), enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                Text(note, color = SpesColors.text3, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            }
            HorizontalDivider(color = SpesColors.line)
            Box(Modifier.weight(1f)) {
                AnimatedContent(tab, transitionSpec = { fadeIn(tween(200)) togetherWith fadeOut(tween(140)) }, label = "tab") { t ->
                    when (t) {
                        Tab.Chat -> ChatTab(state, onMode = { act("mode", JSONObject().put("agent", it), "Mod değişti") },
                            onSent = { refresh++ }, onNote = { note = it })
                        Tab.Team -> TeamTab(overview, state, onModel = { agent, model, effort ->
                            act("model", JSONObject().put("agent", agent).apply { model?.let { put("model", it) }; effort?.let { put("effort", it) } }, "Model ayarı kaydedildi")
                        })
                        Tab.Work -> WorkTab(overview)
                        Tab.List -> ListTab(state, overview,
                            onNew = { act("new", JSONObject().put("agent", "collaboration"), "Yeni sohbet açıldı"); tab = Tab.Chat },
                            onSelect = { act("select", JSONObject().put("conversation_id", it)); tab = Tab.Chat },
                            onProject = { act("project", JSONObject().put("project_id", it), "Proje değişti") })
                    }
                }
            }
            NavigationBar(containerColor = SpesColors.surface1, tonalElevation = 0.dp) {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t, onClick = { tab = t },
                        icon = { Box(Modifier.size(if (tab == t) 10.dp else 7.dp).clip(CircleShape).background(if (tab == t) SpesColors.accent else SpesColors.text3)) },
                        label = { Text(t.label, fontSize = 12.sp) },
                        colors = NavigationBarItemDefaults.colors(selectedTextColor = SpesColors.text, unselectedTextColor = SpesColors.text3,
                            indicatorColor = SpesColors.surface3),
                    )
                }
            }
        }
    }

    @Composable
    private fun StatusBar(state: SpesApi.State?, onStop: () -> Unit) {
        val busy = state?.busy == true
        val color by animateColorAsState(if (busy) SpesColors.fatum else SpesColors.accent, tween(400), label = "status")
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            PulseDot(color, busy)
            Spacer(Modifier.width(10.dp))
            AnimatedContent(when {
                state == null -> "Bağlanıyor"
                busy -> state.progress.ifBlank { if (state.working.isNotEmpty()) state.working.joinToString(" ve ") + " çalışıyor" else "Ekip çalışıyor" }
                else -> "Ekip hazır"
            }, transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(140)) }, label = "statusText", modifier = Modifier.weight(1f)) {
                Text(it, color = SpesColors.text2, fontSize = 14.sp, maxLines = 2)
            }
            Button(onClick = onStop, colors = ButtonDefaults.buttonColors(containerColor = SpesColors.stop, contentColor = SpesColors.text),
                modifier = Modifier.height(42.dp), contentPadding = PaddingValues(horizontal = 18.dp)) { Text("Dur") }
        }
    }

    // -- chat --------------------------------------------------------------
    @Composable
    private fun ChatTab(state: SpesApi.State?, onMode: (String) -> Unit, onSent: () -> Unit, onNote: (String) -> Unit) {
        val scope = rememberCoroutineScope()
        var draft by remember { mutableStateOf("") }
        val list = rememberLazyListState()
        val seen = remember { HashSet<String>() }
        var primed by remember { mutableStateOf(false) }
        val messages = state?.messages ?: emptyList()
        // History that was there when the screen opened appears still; only later messages animate in.
        LaunchedEffect(messages.isNotEmpty()) { if (messages.isNotEmpty() && !primed) { messages.forEach { seen.add(it.id) }; primed = true } }
        LaunchedEffect(messages.size, state?.busy) { if (messages.isNotEmpty()) list.animateScrollToItem(messages.size - 1 + if (state?.busy == true) 1 else 0) }

        Column(Modifier.fillMaxSize().imePadding()) {
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MODES.forEach { (key, label) ->
                    val selected = (state?.mode ?: "collaboration") == key
                    FilterChip(selected = selected, onClick = { if (!selected) onMode(key) }, label = { Text(label) },
                        leadingIcon = { Box(Modifier.size(8.dp).clip(CircleShape).background(SpesColors.persona(label).takeIf { key != "collaboration" } ?: SpesColors.accent)) },
                        colors = FilterChipDefaults.filterChipColors(selectedContainerColor = SpesColors.surface3, selectedLabelColor = SpesColors.text,
                            labelColor = SpesColors.text2, containerColor = SpesColors.surface1),
                        border = FilterChipDefaults.filterChipBorder(enabled = true, selected = selected, borderColor = SpesColors.line, selectedBorderColor = SpesColors.accent))
                }
            }
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(messages, key = { it.id + ":" + it.seq }) { m ->
                    val fresh = remember(m.id) { primed && seen.add(m.id) }
                    EnterOnce(fresh) { MessageRow(m) }
                }
                if (state?.busy == true) item(key = "typing") {
                    Row(Modifier.padding(start = 4.dp, top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        TypingDots(SpesColors.text3)
                        Spacer(Modifier.width(10.dp))
                        Text(state.working.joinToString(", ").ifBlank { "Ekip yazıyor" }, color = SpesColors.text3, fontSize = 13.sp)
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(draft, { draft = it }, modifier = Modifier.weight(1f).animateContentSize(),
                    placeholder = { Text("Ekibe yaz (yalnız okuma)") }, maxLines = 5, shape = RoundedCornerShape(18.dp))
                Spacer(Modifier.width(8.dp))
                OutlinedButton(onClick = { startActivity(Intent(this@MainActivity, VoiceActivity::class.java)) },
                    shape = CircleShape, modifier = Modifier.size(52.dp), contentPadding = PaddingValues(0.dp)) {
                    Text("Ses", fontSize = 13.sp, color = SpesColors.text2)
                }
                Spacer(Modifier.width(8.dp))
                val scale by animateFloatAsState(if (draft.isNotBlank()) 1f else .86f, tween(180), label = "send")
                Button(enabled = draft.isNotBlank(), onClick = {
                    val text = draft.trim(); draft = ""; onNote("Gönderiliyor…")
                    scope.launch { onNote(io { api().send(text) }.fold({ "Gönderildi" }, { it.message ?: "Gönderilemedi" })); onSent() }
                }, shape = CircleShape, modifier = Modifier.size(52.dp).graphicsLayer { scaleX = scale; scaleY = scale },
                    contentPadding = PaddingValues(0.dp)) { Text("↑", fontSize = 22.sp) }
            }
        }
    }

    /** New messages rise and fade in once; history loads still. */
    @Composable
    private fun EnterOnce(animate: Boolean, content: @Composable () -> Unit) {
        val progress = remember { Animatable(if (animate) 0f else 1f) }
        LaunchedEffect(Unit) { if (animate) progress.animateTo(1f, tween(320)) }
        Box(Modifier.graphicsLayer { alpha = progress.value; translationY = (1f - progress.value) * 24f }) { content() }
    }

    @Composable
    private fun MessageRow(m: SpesApi.Msg) {
        val mine = m.fromUser
        Column(Modifier.fillMaxWidth(), horizontalAlignment = if (mine) Alignment.End else Alignment.Start) {
            if (mine && m.memory.isNotEmpty()) {
                Row { Tag(if (m.memory == "saved") "Hafızaya alındı" else "Kaydedilmedi: gizli bilgi",
                          if (m.memory == "saved") SpesColors.accent else SpesColors.danger) }
                Spacer(Modifier.height(4.dp))
            }
            if (!mine) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(SpesColors.persona(m.persona)))
                    Spacer(Modifier.width(6.dp))
                    Text(m.persona.ifBlank { "SpeS" }, color = SpesColors.persona(m.persona), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    STEP[m.step]?.let { Tag(it, SpesColors.text3) }
                    if (m.failed) Tag("başarısız", SpesColors.danger)
                }
                Spacer(Modifier.height(4.dp))
            }
            Surface(shape = RoundedCornerShape(if (mine) 18.dp else 14.dp), color = if (mine) SpesColors.surface3 else SpesColors.surface1,
                border = if (m.failed) BorderStroke(1.dp, SpesColors.danger) else null, modifier = Modifier.widthIn(max = 560.dp)) {
                Text(m.text, color = SpesColors.text, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp))
            }
        }
    }

    @Composable
    private fun Tag(text: String, color: Color) {
        Spacer(Modifier.width(8.dp))
        Box(Modifier.clip(RoundedCornerShape(99.dp)).background(SpesColors.surface2).padding(horizontal = 8.dp, vertical = 2.dp)) {
            Text(text, color = color, fontSize = 11.sp)
        }
    }

    // -- team --------------------------------------------------------------
    @Composable
    private fun TeamTab(overview: SpesApi.Overview?, state: SpesApi.State?, onModel: (String, String?, String?) -> Unit) {
        if (overview == null) { Loading(); return }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(overview.agents, key = { it.key }) { agent ->
                val color = SpesColors.persona(agent.persona)
                val working = state?.busy == true && (state.working.contains(agent.persona) || (state.working.isEmpty() && state.progress.contains(agent.persona)))
                Surface(shape = RoundedCornerShape(16.dp), color = SpesColors.surface1, border = BorderStroke(1.dp, if (working) color.copy(alpha = .55f) else SpesColors.line),
                    modifier = Modifier.fillMaxWidth().animateContentSize()) {
                    Column(Modifier.padding(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            PulseDot(color, working, 10.dp)
                            Spacer(Modifier.width(10.dp))
                            Text(agent.persona, color = SpesColors.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.width(8.dp))
                            Text(mapOf("claude" to "Claude", "codex" to "Codex", "antigravity" to "Antigravity")[agent.key] ?: agent.key, color = SpesColors.text3, fontSize = 13.sp)
                            Spacer(Modifier.weight(1f))
                            Text(if (working) "çalışıyor" else "hazır", color = if (working) color else SpesColors.text3, fontSize = 13.sp)
                        }
                        Spacer(Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Picker(agent.model.ifBlank { "Model" }, agent.models) { onModel(agent.key, it, null) }
                            Picker(agent.effort.ifBlank { "Çaba" }, agent.efforts) { onModel(agent.key, null, it) }
                        }
                        overview.limits[agent.key]?.let { LimitBars(it, color) }
                    }
                }
            }
        }
    }

    @Composable
    private fun Picker(label: String, options: List<String>, onPick: (String) -> Unit) {
        var open by remember { mutableStateOf(false) }
        Box {
            OutlinedButton(onClick = { if (options.isNotEmpty()) open = true }, shape = RoundedCornerShape(10.dp),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                Text(label, color = SpesColors.text2, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 150.dp))
            }
            DropdownMenu(open, onDismissRequest = { open = false }) {
                options.forEach { option -> DropdownMenuItem(text = { Text(option) }, onClick = { open = false; onPick(option) }) }
            }
        }
    }

    @Composable
    private fun LimitBars(limit: SpesApi.Limit, color: Color) {
        Spacer(Modifier.height(12.dp))
        if (!limit.available) { Text("Bu ajan limit bilgisi vermiyor", color = SpesColors.text3, fontSize = 12.sp); return }
        listOf("5 saatlik" to limit.fiveHour, "Haftalık" to limit.week).forEach { (name, value) ->
            val target = ((value ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f)
            val shown by animateFloatAsState(target, tween(700), label = name)
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 3.dp)) {
                Text(name, color = SpesColors.text3, fontSize = 12.sp, modifier = Modifier.width(72.dp))
                LinearProgressIndicator(progress = { shown }, modifier = Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(3.dp)),
                    color = if (target > .85f) SpesColors.danger else color, trackColor = SpesColors.surface3, drawStopIndicator = {})
                Text(value?.let { "%${it.toInt()}" } ?: "—", color = SpesColors.text2, fontSize = 12.sp, modifier = Modifier.width(44.dp).padding(start = 8.dp))
            }
        }
    }

    // -- work --------------------------------------------------------------
    @Composable
    private fun WorkTab(overview: SpesApi.Overview?) {
        if (overview == null) { Loading(); return }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Section("Ortam", if (overview.warnings.isEmpty()) "Sorun görünmüyor" else "${overview.warnings.size} uyarı") }
            items(overview.warnings, key = { "w" + it.title }) { w ->
                Card(SpesColors.fatum) {
                    Text(w.title, color = SpesColors.text, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    if (w.fix.isNotBlank()) Text(w.fix, color = SpesColors.text2, fontSize = 13.sp)
                }
            }
            item { Section("Kontroller", "SpeS'in kendisinin gördüğü sonuçlar") }
            if (overview.checks.isEmpty()) item { Empty("Bu sohbette henüz kontrol yok") }
            items(overview.checks.reversed(), key = { "c${it.seq}" }) { c ->
                Card(when (c.tone) { "ok" -> SpesColors.accent; "fail" -> SpesColors.danger; else -> SpesColors.fatum }) {
                    Text(c.label, color = SpesColors.text, fontSize = 14.sp)
                    Text("${c.persona} · #${c.seq} · ${c.files} dosya", color = SpesColors.text3, fontSize = 12.sp)
                }
            }
            item { Section("Değişiklikler", "Ajanın \"değiştirdim\" demesi buraya girmez") }
            if (overview.changes.isEmpty()) item { Empty("Bu sohbette değişen dosya yok") }
            items(overview.changes.reversed(), key = { "f" + it.file }) { f ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(SpesColors.surface1).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(f.file, color = SpesColors.text, fontSize = 13.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${f.persona} · #${f.seq}", color = SpesColors.text3, fontSize = 12.sp)
                }
            }
        }
    }

    @Composable private fun Section(title: String, detail: String) {
        Column(Modifier.padding(top = 10.dp, bottom = 2.dp)) {
            Text(title, color = SpesColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text(detail, color = SpesColors.text3, fontSize = 12.sp)
        }
    }

    @Composable private fun Card(edge: Color, content: @Composable () -> Unit) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(SpesColors.surface1)) {
            Box(Modifier.width(3.dp).height(56.dp).background(edge))
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) { content() }
        }
    }

    @Composable private fun Empty(text: String) = Text(text, color = SpesColors.text3, fontSize = 13.sp, modifier = Modifier.padding(vertical = 4.dp))

    @Composable private fun Loading() {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { TypingDots(SpesColors.text3) }
    }

    // -- conversations -----------------------------------------------------
    @Composable
    private fun ListTab(state: SpesApi.State?, overview: SpesApi.Overview?, onNew: () -> Unit, onSelect: (String) -> Unit, onProject: (String) -> Unit) {
        var list by remember { mutableStateOf<SpesApi.Conversations?>(null) }
        LaunchedEffect(state?.conversationId) { io { api().conversations() }.onSuccess { list = it } }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Button(onClick = onNew, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(14.dp)) { Text("Yeni sohbet") }
            }
            overview?.takeIf { it.projects.size > 1 }?.let { o ->
                item { Section("Proje", o.project?.name ?: "Seçili değil") }
                item {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        o.projects.forEach { p ->
                            FilterChip(selected = p.id == o.project?.id, onClick = { if (p.id != o.project?.id) onProject(p.id) }, label = { Text(p.name) })
                        }
                    }
                }
            }
            item { Section("Sohbetler", "Bilgisayardaki sohbetlerle aynı") }
            if (list == null) item { Box(Modifier.fillMaxWidth().padding(20.dp), contentAlignment = Alignment.Center) { TypingDots(SpesColors.text3) } }
            items(list?.items ?: emptyList(), key = { it.id }) { c ->
                val active = c.id == list?.active
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (active) SpesColors.surface3 else SpesColors.surface1)
                    .clickable { if (!active) onSelect(c.id) }.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(if (active) SpesColors.accent else SpesColors.text3))
                    Spacer(Modifier.width(10.dp))
                    Text(c.title, color = SpesColors.text, fontSize = 15.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(MODES.firstOrNull { it.first == c.agent }?.second ?: "", color = SpesColors.text3, fontSize = 12.sp)
                }
            }
        }
    }

    // -- settings ----------------------------------------------------------
    @Composable
    private fun SettingsScreen(onBack: () -> Unit, onForget: () -> Unit) {
        var watching by remember { mutableStateOf(Prefs.watching(this)) }
        var alarms by remember { mutableStateOf(Prefs.alarms(this)) }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Brand("Ayarlar")
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onBack) { Text("Kapat", color = SpesColors.text2) }
            }
            Text("Bağlı bilgisayar: ${Prefs.url(this@MainActivity)}", color = SpesColors.text3, fontSize = 13.sp)
            SettingRow("Arka planda dinle", "Ekip mesajları ve 'iş bitti' bildirimleri", watching) {
                watching = it; Prefs.setWatching(this@MainActivity, it)
                if (it) WatchService.start(this@MainActivity) else WatchService.stop(this@MainActivity)
            }
            SettingRow("Acil uyarı (arama)", "Bir iş başarısız olunca zil çalar, tam ekran açılır", alarms) {
                alarms = it; Prefs.setAlarms(this@MainActivity, it)
            }
            if (!Notifier.canShowFullScreen(this@MainActivity) && Build.VERSION.SDK_INT >= 34) {
                OutlinedButton(onClick = {
                    startActivity(Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:$packageName")))
                }, modifier = Modifier.fillMaxWidth()) { Text("Tam ekran uyarıya izin ver") }
            }
            OutlinedButton(onClick = { Notifier.alarm(this@MainActivity, "Deneme araması", "SpeS acil uyarısı böyle görünür.") },
                modifier = Modifier.fillMaxWidth()) { Text("Acil uyarıyı dene") }
            MemorySection()
            Text("SpeS ${packageManager.getPackageInfo(packageName, 0).versionName}", color = SpesColors.text3, fontSize = 12.sp)
            Spacer(Modifier.height(12.dp))
            OutlinedButton(onClick = onForget, modifier = Modifier.fillMaxWidth()) { Text("Eşleştirmeyi kaldır", color = SpesColors.danger) }
        }
    }

    /** What the agents remember about you: only what you said "bunu hatırla" for; each line deletable. */
    @Composable
    private fun MemorySection() {
        val scope = rememberCoroutineScope()
        var items by remember { mutableStateOf<List<SpesApi.Memory>?>(null) }
        var reload by remember { mutableIntStateOf(0) }
        LaunchedEffect(reload) { items = io { api().memory() }.getOrNull() ?: emptyList() }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Hafıza", color = SpesColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text("Mesajda \"bunu hatırla\" dediğin bilgiler. Şifre ve kart bilgisi kaydedilmez.", color = SpesColors.text3, fontSize = 12.sp)
            val list = items
            when {
                list == null -> TypingDots(SpesColors.text3)
                list.isEmpty() -> Text("Henüz hatırlanan bir şey yok.", color = SpesColors.text3, fontSize = 13.sp)
                else -> list.asReversed().forEach { item ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(SpesColors.surface1).padding(start = 12.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(item.text, color = SpesColors.text, fontSize = 14.sp, modifier = Modifier.weight(1f))
                        TextButton(onClick = {
                            scope.launch { io { api().act("forget", JSONObject().put("id", item.id)) }; reload++ }
                        }) { Text("Unut", color = SpesColors.danger) }
                    }
                }
            }
        }
    }

    @Composable
    private fun SettingRow(title: String, detail: String, value: Boolean, onChange: (Boolean) -> Unit) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, color = SpesColors.text, fontSize = 16.sp)
                Text(detail, color = SpesColors.text3, fontSize = 13.sp)
            }
            Switch(checked = value, onCheckedChange = onChange)
        }
    }
}
