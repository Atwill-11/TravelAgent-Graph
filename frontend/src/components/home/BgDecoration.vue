<template>
  <div class="bg-decoration">
    <div class="circle circle-1"></div>
    <div class="circle circle-2"></div>
    <div class="circle circle-3"></div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

.circle {
  position: absolute;
  border-radius: 50%;
  animation: float 20s infinite ease-in-out;
}

.circle-1 {
  width: 400px;
  height: 400px;
  top: -150px;
  left: -100px;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.15) 0%,
    rgba(255, 255, 255, 0.05) 70%
  );
}

.circle-2 {
  width: 300px;
  height: 300px;
  top: 40%;
  right: -100px;
  animation-delay: 5s;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.12) 0%,
    rgba(255, 255, 255, 0.04) 70%
  );
}

.circle-3 {
  width: 250px;
  height: 250px;
  bottom: -80px;
  left: 25%;
  animation-delay: 10s;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.1) 0%,
    rgba(255, 255, 255, 0.03) 70%
  );
}

.circle::before {
  content: "";
  position: absolute;
  top: 15%;
  left: 15%;
  width: 25%;
  height: 25%;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 50%;
  filter: blur(20px);
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
  33% {
    transform: translateY(-30px) rotate(120deg) scale(1.05);
  }
  66% {
    transform: translateY(-15px) rotate(240deg) scale(0.95);
  }
}
</style>
