pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

// Producto «Kardex»; el paquete/applicationId com.sebasarchive.kardex se conserva (identificador institucional, cambiarlo rompe instalaciones).
rootProject.name = "kardex"
include(":app")
