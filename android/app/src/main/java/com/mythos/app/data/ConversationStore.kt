package com.mythos.app.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

// --- Entities ---

@Entity(tableName = "messages")
data class MessageEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val sessionId: String,
    val role: String,
    val content: String,
    val timestamp: Long = System.currentTimeMillis(),
    val reasoning: String? = null,
)

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey
    val id: String,
    val title: String = "New Chat",
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val mode: String = "chat",
)

// --- DAOs ---

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages WHERE sessionId = :sessionId ORDER BY timestamp ASC")
    fun getBySession(sessionId: String): Flow<List<MessageEntity>>

    @Query("SELECT * FROM messages WHERE sessionId = :sessionId ORDER BY timestamp ASC")
    suspend fun getBySessionList(sessionId: String): List<MessageEntity>

    @Insert
    suspend fun insert(message: MessageEntity): Long

    @Query("DELETE FROM messages WHERE sessionId = :sessionId")
    suspend fun deleteBySession(sessionId: String)
}

@Dao
interface SessionDao {
    @Query("SELECT * FROM sessions ORDER BY updatedAt DESC")
    fun getAll(): Flow<List<SessionEntity>>

    @Query("SELECT * FROM sessions WHERE id = :id")
    suspend fun getById(id: String): SessionEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(session: SessionEntity)

    @Query("DELETE FROM sessions WHERE id = :id")
    suspend fun delete(id: String)

    @Query("UPDATE sessions SET title = :title, updatedAt = :updatedAt WHERE id = :id")
    suspend fun updateTitle(id: String, title: String, updatedAt: Long = System.currentTimeMillis())
}

// --- Database ---

@Database(entities = [MessageEntity::class, SessionEntity::class], version = 1, exportSchema = false)
abstract class MythosDatabase : RoomDatabase() {
    abstract fun messageDao(): MessageDao
    abstract fun sessionDao(): SessionDao
}

// --- Repository ---

class ConversationStore(
    private val messageDao: MessageDao,
    private val sessionDao: SessionDao,
) {
    fun getMessages(sessionId: String): Flow<List<MessageEntity>> =
        messageDao.getBySession(sessionId)

    suspend fun getMessageList(sessionId: String): List<MessageEntity> =
        messageDao.getBySessionList(sessionId)

    suspend fun addMessage(sessionId: String, role: String, content: String, reasoning: String? = null): Long =
        messageDao.insert(MessageEntity(sessionId = sessionId, role = role, content = content, reasoning = reasoning))

    suspend fun clearSession(sessionId: String) = messageDao.deleteBySession(sessionId)

    fun getAllSessions(): Flow<List<SessionEntity>> = sessionDao.getAll()

    suspend fun createSession(id: String, mode: String = "chat"): SessionEntity {
        val session = SessionEntity(id = id, mode = mode)
        sessionDao.upsert(session)
        return session
    }

    suspend fun updateSessionTitle(id: String, title: String) = sessionDao.updateTitle(id, title)

    suspend fun deleteSession(id: String) {
        messageDao.deleteBySession(id)
        sessionDao.delete(id)
    }

    suspend fun exportAsMarkdown(sessionId: String): String {
        val messages = getMessageList(sessionId)
        val sb = StringBuilder("# Mythos Chat Export\n\n")
        for (msg in messages) {
            val label = when (msg.role) {
                "user" -> "**You**"
                "assistant" -> "**Mythos**"
                "system" -> "**System**"
                else -> msg.role.replaceFirstChar { it.uppercase() }
            }
            sb.append("$label:\n${msg.content}\n\n")
            if (msg.reasoning != null) {
                sb.append("*Thinking:*\n${msg.reasoning}\n\n")
            }
        }
        return sb.toString()
    }
}
