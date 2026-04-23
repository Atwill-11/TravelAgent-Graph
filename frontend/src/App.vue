<template>
  <a-layout style="min-height: 100vh">
    <a-layout-header class="custom-header">
      <div class="header-logo" @click="goHome">
        <span class="logo-icon">🌍</span>
        <span class="logo-text">智能旅游规划助手</span>
      </div>
      <div v-if="isLoggedIn" class="header-user">
        <span class="user-email">{{ userEmail }}</span>
        <a-button class="logout-btn" size="small" @click="handleLogout">退出登录</a-button>
      </div>
      <div v-else class="header-auth">
        <a-button class="login-btn" type="primary" size="small" @click="$router.push('/login')">登录</a-button>
      </div>
    </a-layout-header>
    <a-layout-content style="padding: 0">
      <router-view />
    </a-layout-content>
    <a-layout-footer style="text-align: center; color: #999">
      智能旅游规划助手 ©2025 基于LangGraph框架
    </a-layout-footer>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const userEmail = ref('')

const isLoggedIn = computed(() => !!localStorage.getItem('access_token'))

onMounted(() => {
  userEmail.value = localStorage.getItem('user_email') || ''
})

const goHome = () => {
  router.push('/')
}

const handleLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('session_token')
  localStorage.removeItem('user_email')
  userEmail.value = ''
  router.push('/login')
}
</script>

<style scoped>
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif;
}

.custom-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 0 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
  position: relative;
  z-index: 10;
}

.custom-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(90deg, 
    rgba(255, 255, 255, 0.1) 0%, 
    transparent 50%, 
    rgba(255, 255, 255, 0.05) 100%);
  pointer-events: none;
}

.header-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  z-index: 1;
}

.header-logo:hover {
  transform: scale(1.02);
}

.logo-icon {
  font-size: 32px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
  animation: rotate 20s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.logo-text {
  color: white;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 1px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.header-user {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.user-email {
  color: rgba(255, 255, 255, 0.95);
  font-size: 13px;
  font-weight: 500;
  padding: 4px 14px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 20px;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  line-height: 1.5;
}

.logout-btn {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.1);
  color: white;
  font-weight: 500;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.5);
  color: white;
  transform: translateY(-1px);
}

.header-auth {
  position: relative;
  z-index: 1;
}

.login-btn {
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.95);
  border: none;
  color: #667eea;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
}

.login-btn:hover {
  background: white;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}
</style>
