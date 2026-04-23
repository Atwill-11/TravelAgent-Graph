<template>
  <div class="session-sidebar">
    <div class="sidebar-header">
      <h3>📝 会话管理</h3>
      <a-button
        type="primary"
        size="small"
        @click="handleCreateSession"
        :loading="creating"
      >
        <template #icon>➕</template>
        新建会话
      </a-button>
    </div>

    <div class="session-list">
      <a-spin :spinning="loading">
        <div v-if="sessions.length === 0 && !loading" class="empty-sessions">
          <p>暂无会话</p>
          <p class="hint">点击上方按钮创建新会话</p>
        </div>

        <div
          v-for="session in sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: currentSessionId === session.session_id }"
          @click="selectSession(session)"
        >
          <div class="session-info">
            <div class="session-name">
              {{ session.name || "未命名会话" }}
            </div>
            <div class="session-id">
              {{ session.session_id.slice(0, 8) }}...
            </div>
          </div>
          <div class="session-actions">
            <a-button
              type="text"
              size="small"
              @click.stop="startRename(session)"
              title="重命名"
            >
              ✏️
            </a-button>
            <a-popconfirm
              title="确定删除此会话？"
              @confirm="handleDeleteSession(session.session_id)"
              ok-text="确定"
              cancel-text="取消"
            >
              <a-button
                type="text"
                size="small"
                danger
                @click.stop
                title="删除"
              >
                🗑️
              </a-button>
            </a-popconfirm>
          </div>
        </div>
      </a-spin>
    </div>

    <a-modal
      v-model:open="renameModalVisible"
      title="重命名会话"
      @ok="handleRename"
      @cancel="renameModalVisible = false"
    >
      <a-input
        v-model:value="newName"
        placeholder="请输入会话名称"
        @pressEnter="handleRename"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { message } from "ant-design-vue";
import {
  getSessions,
  createSession,
  updateSessionName,
  deleteSession,
} from "@/services/api";
import type { SessionResponse } from "@/types";

defineProps<{
  currentSessionId?: string;
}>();

const emit = defineEmits<{
  (e: "sessionChange", session: SessionResponse): void;
  (e: "sessionDelete", sessionId: string): void;
}>();

const sessions = ref<SessionResponse[]>([]);
const loading = ref(false);
const creating = ref(false);
const renameModalVisible = ref(false);
const newName = ref("");
const renamingSession = ref<SessionResponse | null>(null);

const loadSessions = async () => {
  loading.value = true;
  try {
    sessions.value = await getSessions();
  } catch (error: any) {
    message.error("加载会话列表失败");
    console.error(error);
  } finally {
    loading.value = false;
  }
};

const handleCreateSession = async () => {
  creating.value = true;
  try {
    const session = await createSession();
    sessions.value.unshift(session);
    emit("sessionChange", session);
    message.success("会话创建成功");
  } catch (error: any) {
    message.error("创建会话失败");
    console.error(error);
  } finally {
    creating.value = false;
  }
};

const selectSession = (session: SessionResponse) => {
  emit("sessionChange", session);
};

const startRename = (session: SessionResponse) => {
  renamingSession.value = session;
  newName.value = session.name || "";
  renameModalVisible.value = true;
};

const handleRename = async () => {
  if (!renamingSession.value || !newName.value.trim()) {
    message.warning("请输入会话名称");
    return;
  }

  try {
    const updated = await updateSessionName(
      renamingSession.value.session_id,
      newName.value.trim(),
    );
    const index = sessions.value.findIndex(
      (s) => s.session_id === updated.session_id,
    );
    if (index !== -1) {
      sessions.value[index] = updated;
    }
    renameModalVisible.value = false;
    message.success("会话重命名成功");
  } catch (error: any) {
    message.error("重命名失败");
    console.error(error);
  }
};

const handleDeleteSession = async (sessionId: string) => {
  try {
    await deleteSession(sessionId);
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId);
    emit("sessionDelete", sessionId);
    message.success("会话已删除");
  } catch (error: any) {
    message.error("删除会话失败");
    console.error(error);
  }
};

onMounted(() => {
  loadSessions();
});

defineExpose({
  loadSessions,
});
</script>

<style scoped>
.session-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.empty-sessions {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.empty-sessions .hint {
  font-size: 12px;
  margin-top: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.session-item:hover {
  background: #f5f5f5;
}

.session-item.active {
  background: #e6f7ff;
  border-color: #1890ff;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-name {
  font-weight: 500;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-id {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.session-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.session-item:hover .session-actions {
  opacity: 1;
}
</style>
