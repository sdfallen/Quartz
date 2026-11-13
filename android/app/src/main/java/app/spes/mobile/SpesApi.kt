package app.spes.mobile

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Client for the SpeS mobile gateway (mobile_server.py) behind Tailscale Serve.
 * The device key goes only in the Authorization header. HTTPS only.
 */
class SpesApi(baseUrl: String, private val token: String) {
    private val base = normalize(baseUrl)

    data class Msg(
        val id: String, val seq: Int, val role: String, val sender: String,
        val persona: String, val step: Int?, val text: String, val failed: Boolean,
    ) {
        val fromUser get() = role == "user" || sender == "user"
    }

    data class State(
        val conversationId: String, val title: String, val busy: Boolean,
        val progress: String, val lastSeq: Int, val messages: List<Msg>,
    )

    fun state(after: Int = 0, waitSeconds: Int = 0): State {
        val json = request("GET", "/api/state?after=$after&wait=$waitSeconds", null, (waitSeconds + 15) * 1000)
        val conv = json.optJSONObject("conversation") ?: JSONObject()
        val rows = json.optJSONArray("messages")
        val list = ArrayList<Msg>()
        if (rows != null) for (i in 0 until rows.length()) {
            val m = rows.getJSONObject(i)
            list += Msg(
                id = m.optString("id"), seq = m.optInt("seq"), role = m.optString("role"),
                sender = m.optString("sender"), persona = m.optString("persona"),
                step = if (m.isNull("step")) null else m.optInt("step"),
                text = m.optString("text"), failed = m.optBoolean("failed"),
            )
        }
        return State(
            conversationId = conv.optString("id"), title = conv.optString("title", "Sohbet"),
            busy = json.optBoolean("busy"), progress = json.optString("progress"),
            lastSeq = json.optInt("last_seq"), messages = list,
        )
    }

    fun send(text: String) {
        request("POST", "/api/send", JSONObject().put("message", text), 20_000)
    }

    fun stop() {
        request("POST", "/api/stop", JSONObject(), 20_000)
    }

    private fun request(method: String, path: String, body: JSONObject?, timeoutMs: Int): JSONObject =
        call(base, method, path, body, timeoutMs, token)

    companion object {
        /** Accepts "pc.tailnet.ts.net", "https://pc.tailnet.ts.net/" and returns "https://pc.tailnet.ts.net". */
        fun normalize(raw: String): String {
            var url = raw.trim().trimEnd('/')
            if (url.isEmpty()) throw IOException("Adres boş")
            if (url.startsWith("http://", ignoreCase = true)) throw IOException("Yalnız https adresi kullanılır (Tailscale Serve)")
            if (!url.startsWith("https://", ignoreCase = true)) url = "https://$url"
            return url
        }

        /** Trades the six-digit code shown on the desktop for the device key. */
        fun pair(baseUrl: String, code: String): String {
            val json = call(normalize(baseUrl), "POST", "/api/pair", JSONObject().put("code", code.trim()), 15_000, null)
            val token = json.optString("token")
            if (token.length < 32) throw IOException("Eşleştirme yanıtı geçersiz")
            return token
        }

        private fun call(base: String, method: String, path: String, body: JSONObject?, timeoutMs: Int, token: String?): JSONObject {
            val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 10_000
                readTimeout = timeoutMs
                useCaches = false
                setRequestProperty("Accept", "application/json")
                if (token != null) setRequestProperty("Authorization", "Bearer $token")
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
            }
            try {
                if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
                val json = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
                if (code == 401) throw AuthException()
                if (code !in 200..299) throw IOException(json.optString("error", "SpeS yanıtı: $code"))
                return json
            } finally {
                connection.disconnect()
            }
        }
    }

    class AuthException : IOException("Cihaz anahtarı geçersiz; yeniden eşleştirin")
}
