import { BaseEntity, Column, Entity, JoinColumn, ManyToOne, PrimaryColumn } from 'typeorm';
import { LicenseDao } from './license.dao';
import { GeoNodeDao } from './geo-node.dao';

@Entity('geo_node_licenses')
export class GeoNodeToLicensesDao extends BaseEntity {
  @PrimaryColumn({ name: 'geo_node_id' })
  geo_node_id: number;

  @Column({ type: 'double precision' })
  latitude: number;

  @Column({ type: 'double precision' })
  longitude: number;

  @PrimaryColumn()
  license_number: string;

  @ManyToOne(() => GeoNodeDao, (geoNode) => geoNode.geoNodeLicenses)
  @JoinColumn({ name: 'geo_node_id' })
  geoNode: GeoNodeDao;

  @ManyToOne(() => LicenseDao, (license) => license.geoNodeLicenses)
  @JoinColumn({ name: 'license_number', referencedColumnName: 'license_number' })
  license: LicenseDao;
}
