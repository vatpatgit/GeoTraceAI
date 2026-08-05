CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(20) DEFAULT 'admin' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    geometry geometry(POLYGON, 4326) NOT NULL,
    center_lat FLOAT NOT NULL,
    center_lng FLOAT NOT NULL,
    area_km2 FLOAT NOT NULL,
    risk_level VARCHAR(20) DEFAULT 'medium' NOT NULL,
    metadata_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS change_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id UUID NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    change_type VARCHAR(30) NOT NULL,
    confidence FLOAT NOT NULL,
    area_affected_km2 FLOAT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    geometry geometry(POLYGON, 4326),
    source VARCHAR(50) DEFAULT 'sentinel-2' NOT NULL,
    ndvi_before FLOAT,
    ndvi_after FLOAT,
    metadata_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    region_id UUID REFERENCES regions(id) ON DELETE CASCADE,
    change_type VARCHAR(30),
    threshold FLOAT DEFAULT 0.7 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_config_id UUID NOT NULL REFERENCES alert_configs(id) ON DELETE CASCADE,
    change_event_id UUID NOT NULL REFERENCES change_events(id) ON DELETE CASCADE,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_change_events_region_id ON change_events(region_id);
CREATE INDEX IF NOT EXISTS idx_change_events_detected_at ON change_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_change_events_change_type ON change_events(change_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_severity ON alert_history(severity);
CREATE INDEX IF NOT EXISTS idx_alert_history_is_read ON alert_history(is_read);


-- Insert Default Admin
INSERT INTO users (id, email, name, role, password_hash, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    'admin@terratrack.dev',
    'Admin',
    'admin',
    '$2b$12$kmM5U5XEqoMYZCospKy/LuQqrvsq8nUnBnYt1N5esM4AMbCmb/5oG',
    NOW()
) ON CONFLICT (email) DO NOTHING;

-- Insert Regions
INSERT INTO regions (id, name, description, geometry, center_lat, center_lng, area_km2, risk_level, created_at)
VALUES 
    (
        '00000000-0000-0000-0000-000000000001',
        'Amazon Basin',
        'The Amazon Basin is the part of South America drained by the Amazon River and its branches.',
        ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[-70.5,-3.5],[-69.0,-5.0],[-65.0,-5.5],[-61.0,-4.5],[-59.5,-2.0],[-59.0,0.5],[-60.0,3.0],[-62.0,5.0],[-65.5,5.5],[-68.5,4.0],[-70.0,1.5],[-70.5,-3.5]]]}'),
        0.0, -64.0, 7000000.0, 'critical', NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000002',
        'Congo Rainforest',
        'The Congolian forests are a broad belt of lowland tropical moist broadleaf forest.',
        ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[18.5,-3.5],[20.0,-4.0],[24.0,-3.5],[27.0,-2.0],[28.5,0.0],[28.0,2.5],[27.0,4.0],[24.5,4.5],[21.0,3.5],[19.0,1.5],[18.0,-1.0],[18.5,-3.5]]]}'),
        0.5, 23.0, 2000000.0, 'high', NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000003',
        'Borneo',
        'Borneo is the third-largest island in the world and the largest in Asia.',
        ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[109.5,-3.0],[111.0,-4.0],[114.5,-4.0],[117.5,-2.5],[119.0,0.5],[118.5,4.0],[117.0,6.5],[114.0,7.0],[111.5,5.5],[109.5,2.5],[108.5,0.0],[109.5,-3.0]]]}'),
        1.5, 114.0, 743000.0, 'high', NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000004',
        'Sahel',
        'The Sahel is the ecoclimatic and biogeographic realm of transition in Africa.',
        ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[-9.5,12.0],[-6.0,10.5],[-2.0,10.0],[3.0,10.5],[7.0,11.0],[10.0,12.5],[10.0,17.5],[7.5,19.5],[3.5,20.0],[-1.0,19.0],[-5.5,18.0],[-9.0,16.0],[-9.5,12.0]]]}'),
        15.0, 0.0, 3053000.0, 'critical', NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000005',
        'Cerrado',
        'The Cerrado is a vast tropical savanna ecoregion of Brazil.',
        ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[-54.0,-7.0],[-50.0,-5.5],[-44.0,-6.5],[-40.5,-9.0],[-40.0,-14.0],[-41.5,-18.0],[-45.0,-20.0],[-50.0,-19.5],[-54.0,-17.0],[-55.5,-13.0],[-55.0,-9.0],[-54.0,-7.0]]]}'),
        -13.0, -48.0, 1916000.0, 'high', NOW()
    )
ON CONFLICT (name) DO NOTHING;
