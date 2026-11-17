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

// Producto «Kardex»; el paquete/applicationId co.edu.umariana.inventario se conserva (identificador institucional, cambiarlo rompe instalaciones).
rootProject.name = "kardex"
include(":app")
