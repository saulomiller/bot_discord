// Modulo: renderiza o background reativo ao audio no dashboard web.

/**
 * Visualizador de fundo reativo ao estado de reproducao do player.
 */
export class AudioReactiveBackground {
    constructor() {
        try {
            this.canvas = document.getElementById('liquid-canvas');
            if (!this.canvas) throw new Error('Canvas element not found');

            this.ctx = this.canvas.getContext('2d');
            this.bars = [];
            this.particles = [];
            this.isPlaying = false;
            this.currentVolume = 0.5;
            this.bassIntensity = 0;
            this.time = 0;

            this.resizeCanvas();
            window.addEventListener('resize', () => this.resizeCanvas());
            this.animate();
            console.log('AudioReactiveBackground initialized');
        } catch (e) {
            console.error('AudioReactiveBackground error:', e);
        }
    }

    /**
     * Ajusta dimensoes do canvas e recalcula barras/particulas.
     */
    resizeCanvas() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;

        const barCount = Math.min(80, Math.floor(this.canvas.width / 15));
        this.bars = [];
        const barWidth = this.canvas.width / barCount;

        for (let i = 0; i < barCount; i++) {
            this.bars.push({
                x: i * barWidth,
                width: barWidth - 3,
                height: 0,
                targetHeight: 0,
                hue: 200 + (i / barCount) * 80, // Azul vibrante a roxo
                speed: 0.15 + Math.random() * 0.15,
                phase: Math.random() * Math.PI * 2,
                energy: 0
            });
        }

        // Inicializar partículas
        this.initParticles();
    }

    initParticles() {
        this.particles = [];
        const particleCount = Math.min(50, Math.floor(this.canvas.width / 30));

        for (let i = 0; i < particleCount; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                size: Math.random() * 2 + 1,
                hue: 200 + Math.random() * 80,
                alpha: Math.random() * 0.5 + 0.3
            });
        }
    }

    animate() {
        this.time += 0.016; // ~60fps

        // Gradiente de fundo dinâmico
        const bgIntensity = this.isPlaying ? 0.3 : 0.1;
        const backgroundGradient = this.ctx.createRadialGradient(
            this.canvas.width / 2, this.canvas.height / 2, 0,
            this.canvas.width / 2, this.canvas.height / 2, this.canvas.width * 0.8
        );

        backgroundGradient.addColorStop(0, `rgba(15, 20, 45, 1)`);
        backgroundGradient.addColorStop(0.5, `rgba(10, 15, 35, 1)`);
        backgroundGradient.addColorStop(1, `rgba(5, 10, 25, 1)`);

        this.ctx.fillStyle = backgroundGradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Desenhar partículas de fundo
        if (this.isPlaying) {
            this.updateAndDrawParticles();
        }

        // Atualizar barras
        if (this.isPlaying) {
            this.updatePlayingBars();
        } else {
            this.updateIdleBars();
        }

        this.drawBars();
        this.drawGlow();

        requestAnimationFrame(() => this.animate());
    }

    updatePlayingBars() {
        const beat = Math.sin(this.time * 2.5) * 0.5 + 0.5; // 0 a 1
        const subBeat = Math.sin(this.time * 5) * 0.3 + 0.5;
        this.bassIntensity = beat * 0.7 + subBeat * 0.3;

        for (let i = 0; i < this.bars.length; i++) {
            const positionFactor = i / this.bars.length;

            // Múltiplas ondas para criar padrão complexo
            const wave1 = Math.sin(this.time * 2 + positionFactor * Math.PI * 4);
            const wave2 = Math.cos(this.time * 3 - positionFactor * Math.PI * 2);
            const wave3 = Math.sin(this.time * 1.5 + positionFactor * Math.PI * 6);

            // Simular frequências diferentes
            const lowFreq = Math.abs(wave1) * (1 - positionFactor * 0.3); // Graves
            const midFreq = Math.abs(wave2) * (0.5 + Math.abs(positionFactor - 0.5)); // Médios
            const highFreq = Math.abs(wave3) * positionFactor; // Agudos

            const combined = (lowFreq * 0.5 + midFreq * 0.3 + highFreq * 0.2);
            const beatBoost = beat * 0.4;

            const amplitude = (0.3 + combined * 0.7 + beatBoost) * (this.currentVolume + 0.3);
            this.bars[i].targetHeight = amplitude * this.canvas.height * 0.5;
            this.bars[i].energy = combined;
        }
    }

    updateIdleBars() {
        for (let i = 0; i < this.bars.length; i++) {
            const positionFactor = i / this.bars.length;

            // Ondas suaves e lentas
            const wave1 = Math.sin(this.time * 0.8 + positionFactor * Math.PI * 2 + this.bars[i].phase);
            const wave2 = Math.sin(this.time * 0.5 - positionFactor * Math.PI * 3);
            const combined = (wave1 * 0.6 + wave2 * 0.4);

            // Altura mínima entre 10% e 25% da tela
            this.bars[i].targetHeight = (0.1 + Math.abs(combined) * 0.15) * this.canvas.height;
            this.bars[i].energy = 0;
        }
    }

    drawBars() {
        const centerY = this.canvas.height * 0.5;
        const smoothing = this.isPlaying ? 0.25 : 0.08;

        for (let bar of this.bars) {
            bar.height = bar.height * (1 - smoothing) + bar.targetHeight * smoothing;

            // Cores vibrantes quando tocando
            const saturation = this.isPlaying ? 90 + bar.energy * 10 : 60;
            const lightness = this.isPlaying ? 60 + bar.energy * 15 : 50;
            const alpha = this.isPlaying ? 0.85 + bar.energy * 0.15 : 0.5;

            // Gradiente vertical mais rico
            const gradient = this.ctx.createLinearGradient(
                bar.x, centerY - bar.height,
                bar.x, centerY + bar.height
            );

            gradient.addColorStop(0, `hsla(${bar.hue}, ${saturation}%, ${lightness + 10}%, ${alpha})`);
            gradient.addColorStop(0.5, `hsla(${bar.hue}, ${saturation}%, ${lightness}%, ${alpha * 0.9})`);
            gradient.addColorStop(1, `hsla(${bar.hue}, ${saturation - 20}%, ${lightness - 20}%, 0)`);

            this.ctx.fillStyle = gradient;

            // Barra superior
            this.ctx.fillRect(bar.x, centerY - bar.height, bar.width, bar.height);

            // Reflexo inferior
            this.ctx.fillRect(bar.x, centerY, bar.width, bar.height);

            // Brilho no topo quando energia alta
            if (this.isPlaying && bar.energy > 0.6) {
                this.ctx.fillStyle = `hsla(${bar.hue}, 100%, 80%, ${(bar.energy - 0.6) * 0.5})`;
                this.ctx.fillRect(bar.x, centerY - bar.height - 2, bar.width, 4);
            }
        }

        // Linha central com brilho
        const lineGlow = this.isPlaying ? this.bassIntensity * 0.3 : 0.1;
        this.ctx.strokeStyle = `rgba(100, 150, 255, ${lineGlow + 0.15})`;
        this.ctx.lineWidth = 2;
        this.ctx.shadowBlur = this.isPlaying ? 10 : 0;
        this.ctx.shadowColor = 'rgba(100, 150, 255, 0.5)';
        this.ctx.beginPath();
        this.ctx.moveTo(0, centerY);
        this.ctx.lineTo(this.canvas.width, centerY);
        this.ctx.stroke();
        this.ctx.shadowBlur = 0;
    }

    drawGlow() {
        if (!this.isPlaying) return;

        const centerY = this.canvas.height * 0.5;

        // Brilho radial no centro quando tocando
        const glowGradient = this.ctx.createRadialGradient(
            this.canvas.width / 2, centerY, 0,
            this.canvas.width / 2, centerY, this.canvas.width * 0.4
        );

        const glowIntensity = this.bassIntensity * 0.15;
        glowGradient.addColorStop(0, `rgba(100, 150, 255, ${glowIntensity})`);
        glowGradient.addColorStop(0.5, `rgba(150, 100, 255, ${glowIntensity * 0.5})`);
        glowGradient.addColorStop(1, 'rgba(100, 150, 255, 0)');

        this.ctx.fillStyle = glowGradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    updateAndDrawParticles() {
        for (let particle of this.particles) {
            // Movimento
            particle.x += particle.vx * (1 + this.bassIntensity);
            particle.y += particle.vy * (1 + this.bassIntensity);

            // Wrap around
            if (particle.x < 0) particle.x = this.canvas.width;
            if (particle.x > this.canvas.width) particle.x = 0;
            if (particle.y < 0) particle.y = this.canvas.height;
            if (particle.y > this.canvas.height) particle.y = 0;

            // Desenhar
            const particleAlpha = particle.alpha * (0.5 + this.bassIntensity * 0.5);
            this.ctx.fillStyle = `hsla(${particle.hue}, 80%, 70%, ${particleAlpha})`;
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();

            // Brilho
            if (this.bassIntensity > 0.5) {
                this.ctx.fillStyle = `hsla(${particle.hue}, 100%, 90%, ${(this.bassIntensity - 0.5) * 0.3})`;
                this.ctx.beginPath();
                this.ctx.arc(particle.x, particle.y, particle.size * 2, 0, Math.PI * 2);
                this.ctx.fill();
            }
        }
    }

    /**
     * Sincroniza estado de reproducao vindo da API com a animacao.
     * @param {boolean} isPlaying
     * @param {number} [volume=0.5]
     */
    syncPlayState(isPlaying, volume = 0.5) {
        this.isPlaying = isPlaying;
        this.currentVolume = Math.max(0, Math.min(1, volume));

        // Reiniciar partículas ao começar a tocar
        if (isPlaying && this.particles.length === 0) {
            this.initParticles();
        }
    }
}
