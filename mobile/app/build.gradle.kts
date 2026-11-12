plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.sebasarchive.kardex"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.sebasarchive.kardex"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true  // Robolectric (Room y SharedPreferences en la JVM)
            all {
                it.testLogging {
                    events("passed", "failed", "skipped")
                    showStandardStreams = false
                }
            }
        }
    }
}

dependencies {
    implementation("androidx.room:room-runtime:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("org.json:json:20240303")  // lee docs/protocol-vectors.json en pruebas JVM puras
}
