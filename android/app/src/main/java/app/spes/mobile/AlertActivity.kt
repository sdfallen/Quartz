package app.spes.mobile

import android.content.Intent
import android.media.AudioAttributes
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.concurrent.thread

/**
 * The "call": rings and vibrates over the lock screen until the user answers, or 45 s pass.
 * Buttons: open SpeS, stop the team's work, or silence.
 */
class AlertActivity : ComponentActivity() {
    private var ringtone: Ringtone? = null
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val title = intent.getStringExtra(EXTRA_TITLE) ?: "SpeS"
        val text = intent.getStringExtra(EXTRA_TEXT) ?: ""
        ring()
        handler.postDelayed({ silence() }, 45_000)
        setContent {
            SpesTheme {
                var stopNote by remember { mutableStateOf("") }
                Column(
                    Modifier.fillMaxSize().background(SpesColors.bg).padding(28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Image(painterResource(R.drawable.ic_launcher_foreground), contentDescription = "SpeS", modifier = Modifier.size(150.dp))
                    Text("SpeS arıyor", color = SpesColors.text3, fontSize = 15.sp)
                    Spacer(Modifier.height(10.dp))
                    Text(title, color = SpesColors.text, fontSize = 24.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(12.dp))
                    Text(text, color = SpesColors.text2, fontSize = 16.sp, textAlign = TextAlign.Center)
                    if (stopNote.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        Text(stopNote, color = SpesColors.accent, fontSize = 14.sp)
                    }
                    Spacer(Modifier.height(36.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Button(
                            onClick = {
                                silence()
                                stopNote = "Durdurma gönderiliyor…"
                                thread {
                                    val ok = runCatching { Prefs.api(this@AlertActivity).stop() }.isSuccess
                                    runOnUiThread { stopNote = if (ok) "Durdurma iletildi" else "Durdurma iletilemedi" }
                                }
                            },
                            modifier = Modifier.weight(1f).height(56.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = SpesColors.stop, contentColor = SpesColors.text),
                        ) { Text("Dur", fontSize = 17.sp) }
                        Button(
                            onClick = {
                                silence()
                                // Answering the "call" opens a voice conversation that starts by saying what happened.
                                startActivity(Intent(this@AlertActivity, VoiceActivity::class.java)
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    .putExtra(VoiceActivity.EXTRA_OPENING, "$title. ${VoiceCommands.forSpeech(text)} Ne yapmak istersin?"))
                                finish()
                            },
                            modifier = Modifier.weight(1f).height(56.dp),
                        ) { Text("Konuş", fontSize = 17.sp) }
                    }
                    Spacer(Modifier.height(12.dp))
                    OutlinedButton(onClick = { silence(); finish() }, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                        Text("Sustur", color = SpesColors.text2)
                    }
                }
            }
        }
    }

    private fun ring() {
        runCatching {
            ringtone = RingtoneManager.getRingtone(this, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE))?.apply {
                audioAttributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE).build()
                isLooping = true
                play()
            }
        }
        runCatching {
            val pattern = longArrayOf(0, 700, 500, 700, 500)
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= 31)
                getSystemService(VibratorManager::class.java).defaultVibrator
            else @Suppress("DEPRECATION") getSystemService(Vibrator::class.java)
            vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0))
        }
    }

    private fun silence() {
        handler.removeCallbacksAndMessages(null)
        runCatching { ringtone?.stop() }
        runCatching {
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= 31)
                getSystemService(VibratorManager::class.java).defaultVibrator
            else @Suppress("DEPRECATION") getSystemService(Vibrator::class.java)
            vibrator.cancel()
        }
        Notifier.cancelAlarm(this)
    }

    override fun onDestroy() {
        silence()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_TITLE = "title"
        const val EXTRA_TEXT = "text"
    }
}
