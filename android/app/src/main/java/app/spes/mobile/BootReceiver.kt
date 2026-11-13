package app.spes.mobile

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Resume listening after the phone restarts, if the user left it on. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) WatchService.start(context)
    }
}
