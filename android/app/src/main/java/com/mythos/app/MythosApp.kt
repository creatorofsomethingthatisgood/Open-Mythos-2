package com.mythos.app

import android.app.Application
import androidx.room.Room
import com.mythos.app.data.ConversationStore
import com.mythos.app.data.MythosDatabase

class MythosApp : Application() {
    val database: MythosDatabase by lazy {
        Room.databaseBuilder(this, MythosDatabase::class.java, "mythos.db").build()
    }

    val conversationStore: ConversationStore by lazy {
        ConversationStore(database.messageDao(), database.sessionDao())
    }
}
