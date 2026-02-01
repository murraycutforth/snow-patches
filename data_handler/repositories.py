"""Repository pattern data access layer for database operations."""

from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from data_handler.models import AOI, SentinelProduct, DownloadStatus, SnowMask


class AOIRepository:
    """Repository for AOI (Area of Interest) data access.

    Provides CRUD operations for AOI records.

    Args:
        session: SQLAlchemy session instance
    """

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        center_lat: float,
        center_lon: float,
        geometry: str,
        size_km: float = 10.0
    ) -> AOI:
        """Create a new AOI record.

        Args:
            name: Unique name for the AOI
            center_lat: Latitude of center point
            center_lon: Longitude of center point
            geometry: WKT string of the AOI boundary
            size_km: Size of AOI in kilometers

        Returns:
            Created AOI instance

        Raises:
            IntegrityError: If AOI name already exists
        """
        aoi = AOI(
            name=name,
            center_lat=center_lat,
            center_lon=center_lon,
            geometry=geometry,
            size_km=size_km
        )
        self.session.add(aoi)
        self.session.commit()
        self.session.refresh(aoi)
        return aoi

    def get_by_name(self, name: str) -> Optional[AOI]:
        """Retrieve AOI by name.

        Args:
            name: AOI name to search for

        Returns:
            AOI instance if found, None otherwise
        """
        return self.session.query(AOI).filter(AOI.name == name).first()

    def get_all(self) -> List[AOI]:
        """Retrieve all AOI records.

        Returns:
            List of all AOI instances
        """
        return self.session.query(AOI).all()

    def exists(self, name: str) -> bool:
        """Check if an AOI with the given name exists.

        Args:
            name: AOI name to check

        Returns:
            True if AOI exists, False otherwise
        """
        return self.session.query(AOI).filter(AOI.name == name).count() > 0


class SentinelProductRepository:
    """Repository for Sentinel-2 product data access.

    Provides CRUD operations and filtering for Sentinel-2 products.

    Args:
        session: SQLAlchemy session instance
    """

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        product_id: str,
        aoi_id: int,
        acquisition_dt: datetime,
        cloud_cover: float,
        geometry: str
    ) -> SentinelProduct:
        """Create a new Sentinel-2 product record.

        Args:
            product_id: Unique Sentinel-2 product identifier
            aoi_id: Foreign key to AOI
            acquisition_dt: Acquisition timestamp
            cloud_cover: Cloud coverage percentage (0-100)
            geometry: GeoJSON string of product footprint

        Returns:
            Created SentinelProduct instance

        Raises:
            IntegrityError: If product_id already exists or aoi_id is invalid
        """
        product = SentinelProduct(
            product_id=product_id,
            aoi_id=aoi_id,
            acquisition_dt=acquisition_dt,
            cloud_cover=cloud_cover,
            geometry=geometry
        )
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)
        return product

    def get_by_id(self, id: int) -> Optional[SentinelProduct]:
        """Retrieve product by database ID.

        Args:
            id: Database primary key ID

        Returns:
            SentinelProduct instance if found, None otherwise
        """
        return self.session.query(SentinelProduct).filter(
            SentinelProduct.id == id
        ).first()

    def get_by_product_id(self, product_id: str) -> Optional[SentinelProduct]:
        """Retrieve product by product_id.

        Args:
            product_id: Sentinel-2 product identifier

        Returns:
            SentinelProduct instance if found, None otherwise
        """
        return self.session.query(SentinelProduct).filter(
            SentinelProduct.product_id == product_id
        ).first()

    def exists(self, product_id: str) -> bool:
        """Check if a product with the given product_id exists.

        Args:
            product_id: Product identifier to check

        Returns:
            True if product exists, False otherwise
        """
        return self.session.query(SentinelProduct).filter(
            SentinelProduct.product_id == product_id
        ).count() > 0

    def get_by_aoi(
        self,
        aoi_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_cloud_cover: Optional[float] = None
    ) -> List[SentinelProduct]:
        """Retrieve products for an AOI with optional filters.

        Args:
            aoi_id: AOI identifier
            start_date: Optional start date filter (inclusive)
            end_date: Optional end date filter (inclusive)
            max_cloud_cover: Optional maximum cloud cover percentage

        Returns:
            List of matching SentinelProduct instances
        """
        query = self.session.query(SentinelProduct).filter(
            SentinelProduct.aoi_id == aoi_id
        )

        if start_date is not None:
            query = query.filter(SentinelProduct.acquisition_dt >= start_date)

        if end_date is not None:
            query = query.filter(SentinelProduct.acquisition_dt <= end_date)

        if max_cloud_cover is not None:
            query = query.filter(SentinelProduct.cloud_cover <= max_cloud_cover)

        return query.order_by(SentinelProduct.acquisition_dt).all()

    def bulk_create_if_not_exists(
        self,
        products_data: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """Bulk create products, skipping duplicates.

        This method checks for existing products by product_id and only
        creates new records for products that don't already exist.

        Args:
            products_data: List of dictionaries containing product data.
                Each dict should have: product_id, aoi_id, acquisition_dt,
                cloud_cover, geometry

        Returns:
            Tuple of (created_count, skipped_count)

        Example:
            >>> products_data = [
            ...     {
            ...         'product_id': 'S2A_MSIL2A_...',
            ...         'aoi_id': 1,
            ...         'acquisition_dt': datetime(2024, 1, 15),
            ...         'cloud_cover': 15.5,
            ...         'geometry': '{...}'
            ...     },
            ...     ...
            ... ]
            >>> created, skipped = repo.bulk_create_if_not_exists(products_data)
        """
        created_count = 0
        skipped_count = 0

        for data in products_data:
            product_id = data['product_id']

            # Check if product already exists
            if self.exists(product_id):
                skipped_count += 1
                continue

            # Create new product
            product = SentinelProduct(**data)
            self.session.add(product)
            created_count += 1

        # Commit all new products at once
        if created_count > 0:
            self.session.commit()

        return created_count, skipped_count


class DownloadStatusRepository:
    """Repository for download status data access.

    Provides CRUD operations for tracking download and processing status.

    Args:
        session: SQLAlchemy session instance
    """

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        product_id: int,
        status: str,
        local_path: Optional[str] = None,
        file_size_mb: Optional[float] = None,
        download_start: Optional[datetime] = None,
        download_end: Optional[datetime] = None,
        error_msg: Optional[str] = None,
        retry_count: int = 0
    ) -> DownloadStatus:
        """Create a new download status record.

        Args:
            product_id: Foreign key to SentinelProduct
            status: Download status (pending, downloaded, failed, processing, processed)
            local_path: Optional path to downloaded file
            file_size_mb: Optional file size in megabytes
            download_start: Optional download start timestamp
            download_end: Optional download end timestamp
            error_msg: Optional error message
            retry_count: Number of retry attempts (default 0)

        Returns:
            Created DownloadStatus instance

        Raises:
            IntegrityError: If product_id already has a status or is invalid
        """
        download_status = DownloadStatus(
            product_id=product_id,
            status=status,
            local_path=local_path,
            file_size_mb=file_size_mb,
            download_start=download_start,
            download_end=download_end,
            error_msg=error_msg,
            retry_count=retry_count
        )
        self.session.add(download_status)
        self.session.commit()
        self.session.refresh(download_status)
        return download_status

    def update_status(
        self,
        status_id: int,
        status: Optional[str] = None,
        local_path: Optional[str] = None,
        file_size_mb: Optional[float] = None,
        download_start: Optional[datetime] = None,
        download_end: Optional[datetime] = None,
        error_msg: Optional[str] = None,
        retry_count: Optional[int] = None
    ) -> DownloadStatus:
        """Update an existing download status record.

        Only updates fields that are provided (not None).

        Args:
            status_id: ID of the status record to update
            status: Optional new status value
            local_path: Optional new local path
            file_size_mb: Optional new file size
            download_start: Optional new download start timestamp
            download_end: Optional new download end timestamp
            error_msg: Optional new error message
            retry_count: Optional new retry count

        Returns:
            Updated DownloadStatus instance

        Raises:
            ValueError: If status_id does not exist
        """
        download_status = self.session.query(DownloadStatus).filter(
            DownloadStatus.id == status_id
        ).first()

        if not download_status:
            raise ValueError(f"Download status with id {status_id} not found")

        # Update only provided fields
        if status is not None:
            download_status.status = status
        if local_path is not None:
            download_status.local_path = local_path
        if file_size_mb is not None:
            download_status.file_size_mb = file_size_mb
        if download_start is not None:
            download_status.download_start = download_start
        if download_end is not None:
            download_status.download_end = download_end
        if error_msg is not None:
            download_status.error_msg = error_msg
        if retry_count is not None:
            download_status.retry_count = retry_count

        self.session.commit()
        self.session.refresh(download_status)
        return download_status

    def get_pending(self) -> List[DownloadStatus]:
        """Retrieve all download status records with status='pending'.

        Returns:
            List of DownloadStatus instances with pending status
        """
        return self.session.query(DownloadStatus).filter(
            DownloadStatus.status == 'pending'
        ).all()

    def get_by_status(self, status: str) -> List[DownloadStatus]:
        """Retrieve all download status records with a specific status.

        Args:
            status: Status to filter by (e.g., 'downloaded', 'pending', 'failed')

        Returns:
            List of DownloadStatus instances with matching status
        """
        return self.session.query(DownloadStatus).filter(
            DownloadStatus.status == status
        ).all()

    def get_by_product_id(self, product_id: int) -> Optional[DownloadStatus]:
        """Retrieve download status for a specific product.

        Args:
            product_id: Product database ID

        Returns:
            DownloadStatus instance if found, None otherwise
        """
        return self.session.query(DownloadStatus).filter(
            DownloadStatus.product_id == product_id
        ).first()


class SnowMaskRepository:
    """Repository for snow mask data access.

    Provides CRUD operations for snow mask records.

    Args:
        session: SQLAlchemy session instance
    """

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        product_id: int,
        ndsi_threshold: float,
        snow_pixels: int,
        total_pixels: int,
        snow_pct: float,
        mask_path: Optional[str] = None
    ) -> SnowMask:
        """Create new snow mask record.

        Args:
            product_id: Foreign key to SentinelProduct
            ndsi_threshold: NDSI threshold used for classification
            snow_pixels: Number of snow pixels
            total_pixels: Total number of pixels
            snow_pct: Snow coverage percentage
            mask_path: Optional path to saved mask file

        Returns:
            Created SnowMask instance

        Raises:
            IntegrityError: If (product_id, ndsi_threshold) combination already exists
        """
        snow_mask = SnowMask(
            product_id=product_id,
            ndsi_threshold=ndsi_threshold,
            snow_pixels=snow_pixels,
            total_pixels=total_pixels,
            snow_pct=snow_pct,
            mask_path=mask_path
        )
        self.session.add(snow_mask)
        self.session.commit()
        self.session.refresh(snow_mask)
        return snow_mask

    def get_by_product_and_threshold(
        self,
        product_id: int,
        ndsi_threshold: float
    ) -> Optional[SnowMask]:
        """Get mask for specific product and threshold.

        Args:
            product_id: Product database ID
            ndsi_threshold: NDSI threshold value

        Returns:
            SnowMask instance if found, None otherwise
        """
        return self.session.query(SnowMask).filter(
            SnowMask.product_id == product_id,
            SnowMask.ndsi_threshold == ndsi_threshold
        ).first()

    def get_by_product(self, product_id: int) -> List[SnowMask]:
        """Get all masks for a product (all thresholds).

        Args:
            product_id: Product database ID

        Returns:
            List of SnowMask instances for this product
        """
        return self.session.query(SnowMask).filter(
            SnowMask.product_id == product_id
        ).order_by(SnowMask.ndsi_threshold).all()

    def exists(self, product_id: int, ndsi_threshold: float) -> bool:
        """Check if mask exists for product and threshold.

        Args:
            product_id: Product database ID
            ndsi_threshold: NDSI threshold value

        Returns:
            True if mask exists, False otherwise
        """
        return self.session.query(SnowMask).filter(
            SnowMask.product_id == product_id,
            SnowMask.ndsi_threshold == ndsi_threshold
        ).count() > 0

    def get_all(self) -> List[SnowMask]:
        """Get all snow mask records.

        Returns:
            List of all SnowMask instances
        """
        return self.session.query(SnowMask).all()
