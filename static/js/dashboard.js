async function initDashboardMap() {
    const runData = window.runData || [];

    if (!runData.length) {
        return;
    }

    const { Map } = await google.maps.importLibrary("maps");
    const { AdvancedMarkerElement } = await google.maps.importLibrary("marker");

    const map = new Map(document.getElementById("map"), {
        center: runData[0].path[0],
        zoom: 13,
        mapTypeControl: true,
        streetViewControl: false,
        fullscreenControl: true,
    });

    const bounds = new google.maps.LatLngBounds();

    const colors = ["#198754", "#0d6efd", "#dc3545", "#fd7e14", "#6f42c1"];

    runData.forEach((run, index) => {
        const color = colors[index % colors.length];
        const path = run.path;

        const polyline = new google.maps.Polyline({
            path: path,
            geodesic: true,
            strokeColor: color,
            strokeOpacity: 0.9,
            strokeWeight: 4,
            map: map,
        });

        const startPoint = path[0];
        const endPoint = path[path.length - 1];

        new AdvancedMarkerElement({
            map: map,
            position: startPoint,
            title: `${run.title} start`,
        });

        new AdvancedMarkerElement({
            map: map,
            position: endPoint,
            title: `${run.title} finish`,
        });

        polyline.addListener("click", () => {
            alert(
                `${run.title}\nDate: ${run.date}\nDistance: ${run.distance_km} km\nDuration: ${run.duration_min} min`
            );
        });

        path.forEach((point) => bounds.extend(point));
    });

    map.fitBounds(bounds);
}

initDashboardMap();