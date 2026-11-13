plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "app.spes.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.spes.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 4
        versionName = "0.3.1"
    }

    // The release key lives only on the build computer (scripts/build_android_apk.py);
    // it is never committed. Without it the build falls back to the debug key.
    val keystore = System.getenv("SPES_KEYSTORE")
    signingConfigs {
        if (keystore != null) {
            create("local") {
                storeFile = file(keystore)
                storePassword = System.getenv("SPES_KEYSTORE_PASSWORD")
                keyAlias = "spes"
                keyPassword = System.getenv("SPES_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("local") ?: signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
}
