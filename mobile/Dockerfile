# Compila y prueba la APK sin instalar nada en el host: JDK 17 + Android SDK + Gradle.
# No copia código: el proyecto se monta en /work (ver servicio `apk-build` en docker-compose.yml).
FROM eclipse-temurin:17-jdk-jammy

RUN apt-get update \
 && apt-get install -y --no-install-recommends unzip curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Android command-line tools (descarga oficial de Google) + lo que pide AGP 8.5: plataforma 34 y build-tools 34.0.0.
ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk
ARG CMDLINE_TOOLS=11076708
RUN mkdir -p "$ANDROID_HOME/cmdline-tools" \
 && curl -fsSL -o /tmp/tools.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
 && unzip -q /tmp/tools.zip -d "$ANDROID_HOME/cmdline-tools" \
 && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
 && rm /tmp/tools.zip \
 && (yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses > /dev/null) \
 && "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" "platforms;android-34" "build-tools;34.0.0" > /dev/null \
 && chmod -R a+rX "$ANDROID_HOME"

# Gradle solo se usa para generar el wrapper (`gradle wrapper`); el build corre con ./gradlew.
ARG GRADLE_VERSION=8.7
RUN curl -fsSL -o /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
 && unzip -q /tmp/gradle.zip -d /opt \
 && rm /tmp/gradle.zip \
 && ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle

# Caché de Gradle, ~/.m2 de Robolectric y la llave de firma debug (~/.android): en un volumen,
# escribible por el usuario sin privilegios con el que corre el contenedor.
# Ese usuario (uid del host) no existe en /etc/passwd y Java no mira $HOME: sin -Duser.home la JVM
# usa «?» como carpeta personal y Robolectric no puede guardar su descarga.
ENV GRADLE_USER_HOME=/gradle-home \
    HOME=/gradle-home \
    JAVA_TOOL_OPTIONS=-Duser.home=/gradle-home
RUN mkdir -p /gradle-home && chmod 777 /gradle-home

WORKDIR /work/mobile
