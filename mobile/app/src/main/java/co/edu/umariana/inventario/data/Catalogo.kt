package co.edu.umariana.inventario.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Transaction

@Entity(tableName = "conteos")
data class ConteoEntity(@PrimaryKey val id: String, val nombre: String)

@Entity(tableName = "productos")
data class ProductoEntity(@PrimaryKey val sku: String, val nombre: String, val categoria: String, val unidad: String)

/** Lo que el PC envía para poder contar. Nunca trae el stock del sistema (conteo ciego, D12). */
data class Catalog(
    val conteos: List<ConteoEntity> = emptyList(),
    val productos: List<ProductoEntity> = emptyList(),
)

@Dao
abstract class CatalogDao {
    @Query("DELETE FROM conteos") protected abstract fun borrarConteos()
    @Query("DELETE FROM productos") protected abstract fun borrarProductos()

    @Insert(onConflict = OnConflictStrategy.REPLACE) protected abstract fun insertarConteos(filas: List<ConteoEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) protected abstract fun insertarProductos(filas: List<ProductoEntity>)

    /** Todo o nada: el catálogo local nunca queda a medias. */
    @Transaction
    open fun reemplazarTodo(catalogo: Catalog) {
        borrarConteos()
        borrarProductos()
        insertarConteos(catalogo.conteos)
        insertarProductos(catalogo.productos)
    }

    @Query("SELECT * FROM conteos ORDER BY id") abstract fun conteos(): List<ConteoEntity>
    @Query("SELECT * FROM productos ORDER BY sku") abstract fun productos(): List<ProductoEntity>
    @Query("SELECT * FROM productos WHERE sku = :sku") abstract fun producto(sku: String): ProductoEntity?
}

/** Catálogo local: se reemplaza entero en cada sincronización con lo que manda el PC. */
class CatalogRepository(private val dao: CatalogDao) {
    fun reemplazarTodo(catalogo: Catalog) = dao.reemplazarTodo(catalogo)
    fun conteos(): List<ConteoEntity> = dao.conteos()
    fun productos(): List<ProductoEntity> = dao.productos()
    fun producto(sku: String): ProductoEntity? = dao.producto(sku)
}
