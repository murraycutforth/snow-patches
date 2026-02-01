"""SQLAlchemy ORM models for snow patch tracking database."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class AOI(Base):
    """Area of Interest model.

    Represents a geographic region for monitoring snow cover.
    Currently tracks Ben Nevis and Ben Macdui mountain regions.

    Attributes:
        id: Primary key
        name: Unique name for the AOI (e.g., "Ben Nevis")
        center_lat: Latitude of AOI center point
        center_lon: Longitude of AOI center point
        geometry: WKT string representing the AOI boundary polygon
        size_km: Size of the AOI in kilometers (default 10.0)
        created_at: Timestamp when the AOI was created
        products: Relationship to SentinelProduct records
    """
    __tablename__ = 'aois'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    geometry = Column(Text, nullable=False)
    size_km = Column(Float, nullable=False, default=10.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    products = relationship("SentinelProduct", back_populates="aoi")

    def __repr__(self):
        return f"<AOI(id={self.id}, name='{self.name}', center=({self.center_lat}, {self.center_lon}))>"


class SentinelProduct(Base):
    """Sentinel-2 satellite product model.

    Represents a discovered Sentinel-2 imagery product for an AOI.

    Attributes:
        id: Primary key
        product_id: Unique Sentinel-2 product identifier
        aoi_id: Foreign key to AOI table
        acquisition_dt: Timestamp when the imagery was acquired
        cloud_cover: Cloud coverage percentage (0-100)
        geometry: GeoJSON string representing the product footprint
        discovered_at: Timestamp when the product was discovered/added to database
        aoi: Relationship to AOI record
        download_status: Relationship to DownloadStatus record (1:1)
        snow_masks: Relationship to SnowMask records
    """
    __tablename__ = 'sentinel_products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String, unique=True, nullable=False)
    aoi_id = Column(Integer, ForeignKey('aois.id'), nullable=False)
    acquisition_dt = Column(DateTime, nullable=False)
    cloud_cover = Column(Float, nullable=False)
    geometry = Column(Text, nullable=False)
    discovered_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        CheckConstraint('cloud_cover >= 0 AND cloud_cover <= 100', name='check_cloud_cover_range'),
    )

    # Relationships
    aoi = relationship("AOI", back_populates="products")
    download_status = relationship("DownloadStatus", back_populates="product", uselist=False)
    snow_masks = relationship("SnowMask", back_populates="product")

    def __repr__(self):
        return f"<SentinelProduct(id={self.id}, product_id='{self.product_id}', cloud_cover={self.cloud_cover}%)>"


class DownloadStatus(Base):
    """Download status model for tracking Sentinel-2 product downloads.

    Tracks the download and processing status of satellite imagery products.
    Used in Phase 4 (Data Download & Processing).

    Attributes:
        id: Primary key
        product_id: Foreign key to SentinelProduct (1:1 relationship)
        status: Current status (pending, downloaded, failed, processing, processed)
        local_path: File path to downloaded data (if downloaded)
        file_size_mb: Size of downloaded file in megabytes
        download_start: Timestamp when download started
        download_end: Timestamp when download completed
        error_msg: Error message if download failed
        retry_count: Number of retry attempts
        updated_at: Timestamp of last status update
        product: Relationship to SentinelProduct record
    """
    __tablename__ = 'download_status'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('sentinel_products.id'), unique=True, nullable=False)
    status = Column(String, nullable=False)
    local_path = Column(Text, nullable=True)
    file_size_mb = Column(Float, nullable=True)
    download_start = Column(DateTime, nullable=True)
    download_end = Column(DateTime, nullable=True)
    error_msg = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'downloaded', 'failed', 'processing', 'processed')",
            name='check_status_valid'
        ),
    )

    # Relationships
    product = relationship("SentinelProduct", back_populates="download_status")

    def __repr__(self):
        return f"<DownloadStatus(id={self.id}, product_id={self.product_id}, status='{self.status}')>"


class SnowMask(Base):
    """Snow mask model for storing snow cover analysis results.

    Stores results of NDSI (Normalized Difference Snow Index) calculations.
    Used in Phase 5 (Snow Mask Generation).

    Attributes:
        id: Primary key
        product_id: Foreign key to SentinelProduct
        ndsi_threshold: NDSI threshold used for snow classification
        snow_pixels: Number of pixels classified as snow
        total_pixels: Total number of valid pixels in the AOI
        snow_pct: Percentage of snow cover
        mask_path: File path to saved snow mask raster
        processing_dt: Timestamp when the mask was generated
        product: Relationship to SentinelProduct record
    """
    __tablename__ = 'snow_masks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('sentinel_products.id'), nullable=False)
    ndsi_threshold = Column(Float, nullable=False)
    snow_pixels = Column(Integer, nullable=False)
    total_pixels = Column(Integer, nullable=False)
    snow_pct = Column(Float, nullable=False)
    mask_path = Column(Text, nullable=True)
    processing_dt = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        UniqueConstraint('product_id', 'ndsi_threshold', name='unique_product_threshold'),
    )

    # Relationships
    product = relationship("SentinelProduct", back_populates="snow_masks")

    def __repr__(self):
        return f"<SnowMask(id={self.id}, product_id={self.product_id}, snow_pct={self.snow_pct}%)>"
