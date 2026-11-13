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
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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

    @Composable
    private fun App() {
        var paired by remember { mutableStateOf(Prefs.paired(this)) }
        var settings by remember { mutableStateOf(false) }
        Box(Modifier.fillMaxSize().background(SpesColors.bg).safeDrawingPadding()) {
            when {
                !paired -> PairScreen { paired = true; WatchService.start(this@MainActivity) }
                settings -> SettingsScreen(onBack = { settings = false }, onForget = {
                    WatchService.stop(this@MainActivity); Prefs.forget(this@MainActivity); settings = false; paired = false
                })
                else -> ChatScreen(onSettings = { settings = true }, onUnpaired = { paired = false })
            }
        }
    }

    @Composable
    private fun Brand(subtitle: String) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.drawable.ic_launcher_foreground), contentDescription = null, modifier = Modifier.size(44.dp))
            Column {
                Text("SpeS", color = SpesColors.text, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = SpesColors.text3, fontSize = 13.sp)
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
            Brand("Telefonu bilgisayarındaki SpeS ile eşleştir")
            Spacer(Modifier.height(28.dp))
            Text(
                "1. Bilgisayarda SpeS → Durum ve araçlar → Araçlar → Mobil erişim'i aç.\n" +
                    "2. Tailscale adresini ve 6 haneli eşleştirme kodunu buraya yaz.",
                color = SpesColors.text2, fontSize = 14.sp, lineHeight = 21.sp,
            )
            Spacer(Modifier.height(20.dp))
            OutlinedTextField(
                value = url, onValueChange = { url = it.trim() }, singleLine = true,
                label = { Text("Tailscale adresi") }, placeholder = { Text("bilgisayar.tailnet.ts.net") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = code, onValueChange = { code = it.filter(Char::isDigit).take(6) }, singleLine = true,
                label = { Text("Eşleştirme kodu") }, placeholder = { Text("6 hane") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), modifier = Modifier.fillMaxWidth(),
            )
            if (error.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text(error, color = SpesColors.danger, fontSize = 14.sp)
            }
            Spacer(Modifier.height(20.dp))
            Button(
                enabled = !busy && url.isNotBlank() && code.length == 6,
                onClick = {
                    busy = true; error = ""
                    scope.launch {
                        val result = withContext(Dispatchers.IO) {
                            runCatching {
                                val base = SpesApi.normalize(url)
                                base to SpesApi.pair(base, code)
                            }
                        }
                        busy = false
                        result.onSuccess { (base, token) -> Prefs.savePairing(this@MainActivity, base, token); onPaired() }
                            .onFailure { error = it.message ?: "Bağlanılamadı" }
                    }
                },
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) { Text(if (busy) "Bağlanıyor…" else "Eşleştir") }
        }
    }

    // -- conversation ------------------------------------------------------
    @Composable
    private fun ChatScreen(onSettings: () -> Unit, onUnpaired: () -> Unit) {
        val scope = rememberCoroutineScope()
        var state by remember { mutableStateOf<SpesApi.State?>(null) }
        var error by remember { mutableStateOf("") }
        var draft by remember { mutableStateOf("") }
        var note by remember { mutableStateOf("") }
        var tick by remember { mutableIntStateOf(0) }
        val list = rememberLazyListState()

        LaunchedEffect(tick) {
            while (true) {
                val result = withContext(Dispatchers.IO) { runCatching { Prefs.api(this@MainActivity).state(0, 0) } }
                result.onSuccess { state = it; error = "" }.onFailure {
                    if (it is SpesApi.AuthException) { Prefs.forget(this@MainActivity); onUnpaired(); return@LaunchedEffect }
                    error = "Bilgisayara ulaşılamıyor. Tailscale açık ve SpeS çalışıyor mu?"
                }
                delay(if (state?.busy == true) 2_000 else 4_000)
            }
        }
        LaunchedEffect(state?.lastSeq) { state?.messages?.size?.let { if (it > 0) list.animateScrollToItem(it - 1) } }

        Column(Modifier.fillMaxSize().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Brand(state?.title ?: "Bağlanıyor…")
                }
                TextButton(onClick = onSettings) { Text("Ayarlar", color = SpesColors.text2) }
            }
            StatusBar(state, onStop = {
                note = "Durdurma gönderiliyor…"
                scope.launch {
                    val ok = withContext(Dispatchers.IO) { runCatching { Prefs.api(this@MainActivity).stop() }.isSuccess }
                    note = if (ok) "Durdurma iletildi" else "Durdurma iletilemedi"
                    tick++
                }
            })
            if (error.isNotEmpty()) Text(error, color = SpesColors.danger, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp))
            if (note.isNotEmpty()) Text(note, color = SpesColors.text3, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            HorizontalDivider(color = SpesColors.line)
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, contentPadding = androidx.compose.foundation.layout.PaddingValues(14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(state?.messages ?: emptyList(), key = { it.id + it.seq }) { MessageRow(it) }
            }
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = draft, onValueChange = { draft = it }, modifier = Modifier.weight(1f),
                    placeholder = { Text("Ekibe yaz (yalnız okuma)") }, maxLines = 4,
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    enabled = draft.isNotBlank(),
                    onClick = {
                        val text = draft.trim(); draft = ""; note = "Gönderiliyor…"
                        scope.launch {
                            val r = withContext(Dispatchers.IO) { runCatching { Prefs.api(this@MainActivity).send(text) } }
                            note = r.fold({ "Gönderildi" }, { it.message ?: "Gönderilemedi" }); tick++
                        }
                    },
                    shape = CircleShape, modifier = Modifier.size(52.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                ) { Text("↑", fontSize = 22.sp) }
            }
        }
    }

    @Composable
    private fun StatusBar(state: SpesApi.State?, onStop: () -> Unit) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(9.dp).clip(CircleShape).background(if (state?.busy == true) SpesColors.fatum else SpesColors.accent))
            Spacer(Modifier.width(8.dp))
            Text(
                when {
                    state == null -> "Bağlanıyor"
                    state.busy -> state.progress.ifBlank { "Ekip çalışıyor" }
                    else -> "Ekip hazır"
                },
                color = SpesColors.text2, fontSize = 14.sp, modifier = Modifier.weight(1f), maxLines = 2,
            )
            // Stop is always reachable, like on the desktop.
            Button(onClick = onStop, colors = ButtonDefaults.buttonColors(containerColor = SpesColors.stop, contentColor = SpesColors.text),
                modifier = Modifier.height(44.dp)) { Text("Dur") }
        }
    }

    @Composable
    private fun MessageRow(m: SpesApi.Msg) {
        val mine = m.fromUser
        Column(Modifier.fillMaxWidth(), horizontalAlignment = if (mine) Alignment.End else Alignment.Start) {
            if (!mine) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(SpesColors.persona(m.persona)))
                    Spacer(Modifier.width(6.dp))
                    Text(m.persona.ifBlank { "SpeS" }, color = SpesColors.persona(m.persona), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    if (m.failed) Text("  · başarısız", color = SpesColors.danger, fontSize = 13.sp)
                }
                Spacer(Modifier.height(4.dp))
            }
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = if (mine) SpesColors.surface3 else SpesColors.surface1,
                border = if (m.failed) BorderStroke(1.dp, SpesColors.danger) else null,
                modifier = Modifier.widthIn(max = 520.dp),
            ) {
                Text(m.text, color = SpesColors.text, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(12.dp))
            }
        }
    }

    // -- settings ----------------------------------------------------------
    @Composable
    private fun SettingsScreen(onBack: () -> Unit, onForget: () -> Unit) {
        var watching by remember { mutableStateOf(Prefs.watching(this)) }
        var alarms by remember { mutableStateOf(Prefs.alarms(this)) }
        Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
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
            Spacer(Modifier.weight(1f))
            OutlinedButton(onClick = onForget, modifier = Modifier.fillMaxWidth()) { Text("Eşleştirmeyi kaldır", color = SpesColors.danger) }
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
