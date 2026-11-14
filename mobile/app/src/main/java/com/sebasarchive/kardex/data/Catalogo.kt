package com.sebasarchive.kardex.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Transaction

/**
 * Una tarea de conteo asignada al operador (o un conteo general, sin almacén ni estado). [estado] es el del PC
 * (`ASIGNADA`, `EN_PROGRESO`...); [total] y [contados], su avance al momento de sincronizar.
 */
@Entity(tableName = "tareas")
data class TareaEntity(
    @PrimaryKey val id: String,
    val nombre: String,
    val almacen: String,
    val instrucciones: String,
    val estado: String,
    val total: Int,
    val contados: Int,
) {
    val esGeneral: Boolean get() = estado.isEmpty()
}

/** Un producto que la tarea pide verificar; [recuento] si Inventario pidió contarlo de nuevo. */
@Entity(tableName = "items_tarea", primaryKeys = ["idTarea", "sku"])
data class ItemTareaEntity(val idTarea: String, val sku: String, val recuento: Boolean)

/** El operador empezó esta tarea en el teléfono. Es local: el catálogo nuevo no la borra. */
@Entity(tableName = "inicios")
data class InicioEntity(@PrimaryKey val idTarea: String)

@Entity(tableName = "productos")
data class ProductoEntity(@PrimaryKey val sku: String, val nombre: String, val categoria: String, val unidad: String)

/** Lo que el PC envía para poder contar. Nunca trae el stock del sistema (conteo ciego, D12). */
data class Catalog(
    val tareas: List<TareaEntity> = emptyList(),
    val items: List<ItemTareaEntity> = emptyList(),
    val productos: List<ProductoEntity> = emptyList(),
)

@Dao
abstract class CatalogDao {
    @Query("DELETE FROM tareas") protected abstract fun borrarTareas()
    @Query("DELETE FROM items_tarea") protected abstract fun borrarItems()
    @Query("DELETE FROM productos") protected abstract fun borrarProductos()

    @Insert(onConflict = OnConflictStrategy.REPLACE) protected abstract fun insertarTareas(filas: List<TareaEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) protected abstract fun insertarItems(filas: List<ItemTareaEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) protected abstract fun insertarProductos(filas: List<ProductoEntity>)
    @Insert(onConflict = OnConflictStrategy.IGNORE) abstract fun insertarInicio(fila: InicioEntity)

    /** Todo o nada: el catálogo local nunca queda a medias. Los inicios no se tocan. */
    @Transaction
    open fun reemplazarTodo(catalogo: Catalog) {
        borrarTareas()
        borrarItems()
        borrarProductos()
        insertarTareas(catalogo.tareas)
        insertarItems(catalogo.items)
        insertarProductos(catalogo.productos)
    }

    // Las tareas primero y los conteos generales al final; dentro de cada grupo, en el orden del id.
    @Query("SELECT * FROM tareas ORDER BY estado = '', id") abstract fun tareas(): List<TareaEntity>
    @Query("SELECT * FROM items_tarea WHERE idTarea = :idTarea ORDER BY sku") abstract fun items(idTarea: String): List<ItemTareaEntity>
    @Query("SELECT idTarea FROM inicios") abstract fun iniciadas(): List<String>
    @Query("SELECT * FROM productos ORDER BY sku") abstract fun productos(): List<ProductoEntity>
    @Query("SELECT * FROM productos WHERE sku = :sku") abstract fun producto(sku: String): ProductoEntity?
}

/** Catálogo local: se reemplaza entero en cada sincronización con lo que manda el PC. */
class CatalogRepository(private val dao: CatalogDao) {
    fun reemplazarTodo(catalogo: Catalog) = dao.reemplazarTodo(catalogo)
    fun tareas(): List<TareaEntity> = dao.tareas()
    fun items(idTarea: String): List<ItemTareaEntity> = dao.items(idTarea)
    fun marcarIniciada(idTarea: String) = dao.insertarInicio(InicioEntity(idTarea))
    fun iniciadas(): Set<String> = dao.iniciadas().toSet()
    fun productos(): List<ProductoEntity> = dao.productos()
    fun producto(sku: String): ProductoEntity? = dao.producto(sku)
}
