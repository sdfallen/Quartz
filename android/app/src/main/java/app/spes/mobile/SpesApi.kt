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
        val persona: String, val step: Int?, val text: String, val failed: Boolean, val model: String = "",
        val memory: String = "", val report: Boolean = false,
    ) {
        val fromUser get() = role == "user" || sender == "user"
    }

    data class State(
        val conversationId: String, val title: String, val busy: Boolean,
        val progress: String, val lastSeq: Int, val messages: List<Msg>,
        val mode: String = "collaboration", val working: List<String> = emptyList(),
    )

    data class Agent(val key: String, val persona: String, val model: String, val effort: String,
                     val models: List<String>, val efforts: List<String>)
    data class Limit(val fiveHour: Double?, val week: Double?, val state: String, val available: Boolean)
    data class Warning(val title: String, val fix: String)
    data class Change(val file: String, val persona: String, val seq: Int)
    data class Check(val label: String, val tone: String, val persona: String, val seq: Int, val files: Int)
    data class Project(val id: String, val name: String)
    data class Overview(
        val mode: String, val project: Project?, val projects: List<Project>, val agents: List<Agent>,
        val limits: Map<String, Limit>, val healthStatus: String, val warnings: List<Warning>,
        val changes: List<Change>, val checks: List<Check>,
    )
    data class Conversation(val id: String, val title: String, val agent: String)
    data class Conversations(val active: String, val items: List<Conversation>)

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
                text = m.optString("text"), failed = m.optBoolean("failed"), model = m.optString("model"),
                memory = m.optString("memory"), report = m.optBoolean("report"),
            )
        }
        return State(
            conversationId = conv.optString("id"), title = conv.optString("title", "Sohbet"),
            busy = json.optBoolean("busy"), progress = json.optString("progress"),
            lastSeq = json.optInt("last_seq"), messages = list,
            mode = json.optString("mode", "collaboration"), working = strings(json.optJSONArray("working")),
        )
    }

    fun overview(): Overview {
        val json = request("GET", "/api/overview", null, 30_000)
        val agentsJson = json.optJSONObject("agents") ?: JSONObject()
        val agents = listOf("claude", "codex", "antigravity").mapNotNull { key ->
            agentsJson.optJSONObject(key)?.let {
                Agent(key, it.optString("persona"), it.optString("model"), it.optString("effort"),
                    strings(it.optJSONArray("models")), strings(it.optJSONArray("efforts")))
            }
        }
        val limitsJson = json.optJSONObject("limits") ?: JSONObject()
        val limits = HashMap<String, Limit>()
        for (key in limitsJson.keys()) {
            val l = limitsJson.optJSONObject(key) ?: continue
            limits[key] = Limit(
                if (l.isNull("five_hour") || !l.has("five_hour")) null else l.optDouble("five_hour"),
                if (l.isNull("week") || !l.has("week")) null else l.optDouble("week"),
                l.optString("state", "unknown"), l.optString("source") != "unavailable",
            )
        }
        val health = json.optJSONObject("health") ?: JSONObject()
        val evidence = json.optJSONObject("evidence") ?: JSONObject()
        fun objects(name: String, from: JSONObject) = from.optJSONArray(name)?.let { a -> (0 until a.length()).map { a.getJSONObject(it) } } ?: emptyList()
        val project = json.optJSONObject("project")?.takeIf { it.has("id") }?.let { Project(it.optString("id"), it.optString("name")) }
        return Overview(
            mode = json.optString("mode", "collaboration"), project = project,
            projects = objects("projects", json).map { Project(it.optString("id"), it.optString("name")) },
            agents = agents, limits = limits, healthStatus = health.optString("status", "unknown"),
            warnings = objects("warnings", health).map { Warning(it.optString("title"), it.optString("fix")) },
            changes = objects("changes", evidence).map { Change(it.optString("file"), it.optString("persona"), it.optInt("seq")) },
            checks = objects("checks", evidence).map { Check(it.optString("label"), it.optString("tone"), it.optString("persona"), it.optInt("seq"), it.optInt("files")) },
        )
    }

    fun conversations(): Conversations {
        val json = request("GET", "/api/conversations", null, 20_000)
        val items = json.optJSONArray("items")
        val list = ArrayList<Conversation>()
        if (items != null) for (i in 0 until items.length()) {
            val c = items.getJSONObject(i)
            list += Conversation(c.optString("id"), c.optString("title", "Sohbet"), c.optString("agent"))
        }
        return Conversations(json.optString("active"), list)
    }

    data class Memory(val id: String, val text: String)

    fun memory(): List<Memory> {
        val items = request("GET", "/api/memory", null, 20_000).optJSONArray("items") ?: return emptyList()
        return (0 until items.length()).map { items.getJSONObject(it) }.map { Memory(it.optString("id"), it.optString("text")) }
    }

    /** new | select | mode | model | project | forget; never a write permission. */
    fun act(action: String, body: JSONObject = JSONObject()) {
        request("POST", "/api/act/$action", body, 20_000)
    }

    private fun strings(array: org.json.JSONArray?): List<String> =
        if (array == null) emptyList() else (0 until array.length()).map { array.optString(it) }

    /** Voice mode: ("answered" | "team", spoken reply, last sequence before the question). */
    fun voice(text: String): Triple<String, String, Int> {
        val json = request("POST", "/api/voice", JSONObject().put("text", text), 30_000)
        return Triple(json.optString("route", "team"), json.optString("reply"), json.optInt("after"))
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
