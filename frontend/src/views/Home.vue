<template>
  <div class="home-layout">
    <SessionSidebar
      ref="sidebarRef"
      :current-session-id="currentSession?.session_id"
      @session-change="handleSessionChange"
      @session-delete="handleSessionDelete"
    />

    <div class="home-container">
      <BgDecoration />

      <PageHeader :current-session="currentSession" />

      <TripForm :current-session="currentSession" @submit="handleSubmit" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import SessionSidebar from "@/components/SessionSidebar.vue";
import { PageHeader, TripForm, BgDecoration } from "@/components/home";
import { useSession } from "@/composables";

const sidebarRef = ref<InstanceType<typeof SessionSidebar> | null>(null);

const {
  currentSession,
  handleSessionChange,
  handleSessionDelete,
  ensureSession,
} = useSession();

const handleSubmit = async () => {
  await ensureSession(sidebarRef.value);
};
</script>

<style scoped>
.home-layout {
  display: flex;
  min-height: calc(100vh - 64px - 69px);
}

.home-container {
  flex: 1;
  background:
    linear-gradient(
      135deg,
      rgba(102, 126, 234, 0.95) 0%,
      rgba(118, 75, 162, 0.95) 50%,
      rgba(240, 147, 251, 0.9) 100%
    ),
    url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  padding: 60px 40px;
  position: relative;
  overflow: hidden;
}
</style>
