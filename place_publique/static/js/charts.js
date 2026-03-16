/**
 * charts.js — Place Publique / FlowView
 * Fonctions Chart.js pour le dashboard de comptage piétons.
 *
 * Fonctions exportées :
 *   - initComparisonChart(camerasData, canvasId)
 *   - updateComparisonChart(apiData, canvasId)
 *   - initHourlyChart(byHour, canvasId, cameraName)
 */

"use strict";

// Registre des instances Chart.js par canvas ID
const _chartInstances = {};

/**
 * Initialise le graphique comparatif Abbey Road vs Shibuya.
 *
 * @param {Object} camerasData  - Objet {camera_id: {history_24h: [...], ...}}
 * @param {string} canvasId     - ID du canvas HTML
 */
function initComparisonChart(camerasData, canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Extraire les données Abbey Road et Shibuya
  const abbeyData = (camerasData['abbey_road'] || {}).history_24h || [];
  const shibuyaData = (camerasData['shibuya'] || {}).history_24h || [];

  // Union des timestamps pour l'axe X
  const allTimestamps = [
    ...new Set([
      ...abbeyData.map(d => d.timestamp),
      ...shibuyaData.map(d => d.timestamp)
    ])
  ].sort();

  // Mapper les comptages sur les timestamps unifiés
  function buildValues(data, labels) {
    const map = {};
    data.forEach(d => { map[d.timestamp] = d.count; });
    return labels.map(ts => map[ts] !== undefined ? map[ts] : null);
  }

  const labels = allTimestamps.map(ts => {
    // Formatage HH:MM pour l'affichage
    try {
      return ts.slice(11, 16);
    } catch (e) {
      return ts;
    }
  });

  const abbeyValues = buildValues(abbeyData, allTimestamps);
  const shibuyaValues = buildValues(shibuyaData, allTimestamps);

  const chartData = {
    labels: labels.length ? labels : ['Aucune donnée'],
    datasets: [
      {
        label: 'Abbey Road (Londres)',
        data: abbeyValues.length ? abbeyValues : [0],
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88, 166, 255, 0.12)',
        pointBackgroundColor: '#58a6ff',
        tension: 0.3,
        fill: true,
        spanGaps: true,
      },
      {
        label: 'Shibuya (Tokyo)',
        data: shibuyaValues.length ? shibuyaValues : [0],
        borderColor: '#ff7b72',
        backgroundColor: 'rgba(255, 123, 114, 0.12)',
        pointBackgroundColor: '#ff7b72',
        tension: 0.3,
        fill: true,
        spanGaps: true,
      }
    ]
  };

  // Détruire l'instance existante si elle existe
  if (_chartInstances[canvasId]) {
    _chartInstances[canvasId].destroy();
  }

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'line',
    data: chartData,
    options: _lineChartOptions('Piétons détectés'),
  });
}

/**
 * Met à jour le graphique comparatif avec les nouvelles données de l'API.
 *
 * @param {Array}  apiData  - Réponse JSON de /api/counts
 * @param {string} canvasId - ID du canvas HTML
 */
function updateComparisonChart(apiData, canvasId) {
  const chart = _chartInstances[canvasId];
  if (!chart) return;

  // Reconstruire les données à partir de la réponse API
  const camerasData = {};
  apiData.forEach(cam => {
    camerasData[cam.camera_id] = { history_24h: cam.history_24h || [] };
  });

  const abbeyData = (camerasData['abbey_road'] || {}).history_24h || [];
  const shibuyaData = (camerasData['shibuya'] || {}).history_24h || [];

  const allTimestamps = [
    ...new Set([
      ...abbeyData.map(d => d.timestamp),
      ...shibuyaData.map(d => d.timestamp)
    ])
  ].sort();

  function buildValues(data, labels) {
    const map = {};
    data.forEach(d => { map[d.timestamp] = d.count; });
    return labels.map(ts => map[ts] !== undefined ? map[ts] : null);
  }

  const labels = allTimestamps.map(ts => ts.slice(11, 16));

  chart.data.labels = labels.length ? labels : ['Aucune donnée'];
  chart.data.datasets[0].data = buildValues(abbeyData, allTimestamps);
  chart.data.datasets[1].data = buildValues(shibuyaData, allTimestamps);
  chart.update('none'); // Mise à jour sans animation pour la fluidité
}

/**
 * Initialise le graphique en barres par heure pour la page détail caméra.
 *
 * @param {Array}  byHour     - [{hour: int, count: float}, ...]
 * @param {string} canvasId   - ID du canvas HTML
 * @param {string} cameraName - Nom de la caméra pour le label
 */
function initHourlyChart(byHour, canvasId, cameraName) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Créer un tableau de 24 heures avec les comptages
  const hourlyData = new Array(24).fill(0);
  (byHour || []).forEach(d => {
    if (d.hour >= 0 && d.hour < 24) {
      hourlyData[d.hour] = d.count;
    }
  });

  const labels = Array.from({ length: 24 }, (_, i) =>
    String(i).padStart(2, '0') + 'h'
  );

  if (_chartInstances[canvasId]) {
    _chartInstances[canvasId].destroy();
  }

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: cameraName || 'Comptage',
        data: hourlyData,
        backgroundColor: 'rgba(88, 166, 255, 0.5)',
        borderColor: '#58a6ff',
        borderWidth: 1,
        borderRadius: 4,
      }]
    },
    options: _barChartOptions('Piétons/heure'),
  });
}

// ============================================================
// Options Chart.js communes
// ============================================================

function _lineChartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      intersect: false,
      mode: 'index',
    },
    plugins: {
      legend: {
        labels: { color: '#c9d1d9' }
      },
      tooltip: {
        backgroundColor: '#161b22',
        titleColor: '#c9d1d9',
        bodyColor: '#8b949e',
        borderColor: '#30363d',
        borderWidth: 1,
      }
    },
    scales: {
      x: {
        ticks: {
          color: '#8b949e',
          maxTicksLimit: 12,
          maxRotation: 0,
        },
        grid: { color: 'rgba(48, 54, 61, 0.5)' },
      },
      y: {
        title: {
          display: true,
          text: yLabel,
          color: '#8b949e',
        },
        ticks: {
          color: '#8b949e',
          stepSize: 1,
        },
        grid: { color: 'rgba(48, 54, 61, 0.5)' },
        beginAtZero: true,
      }
    }
  };
}

function _barChartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: '#c9d1d9' }
      },
      tooltip: {
        backgroundColor: '#161b22',
        titleColor: '#c9d1d9',
        bodyColor: '#8b949e',
        borderColor: '#30363d',
        borderWidth: 1,
      }
    },
    scales: {
      x: {
        ticks: { color: '#8b949e' },
        grid: { color: 'rgba(48, 54, 61, 0.5)' },
      },
      y: {
        title: {
          display: true,
          text: yLabel,
          color: '#8b949e',
        },
        ticks: {
          color: '#8b949e',
          stepSize: 1,
        },
        grid: { color: 'rgba(48, 54, 61, 0.5)' },
        beginAtZero: true,
      }
    }
  };
}
