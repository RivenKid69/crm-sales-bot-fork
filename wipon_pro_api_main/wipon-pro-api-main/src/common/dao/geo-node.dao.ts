import {
  BaseEntity,
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToMany,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { GeoNodeToLicensesDao } from './geo-node_licenses.dao';
import { RegionDao } from './region.dao';

@Entity('geo_nodes')
export class GeoNodeDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'region_id' })
  region_id: number;

  @Column({ name: 'parent_id' })
  parent_id: number;

  @Column({ name: 'name_ru' })
  name_ru: string;

  @Column({ name: 'name_en' })
  name_en: string;

  @Column({ name: 'name_kk' })
  name_kk: string;

  @Column({ type: 'double precision' })
  latitude: number;

  @Column({ type: 'double precision' })
  longitude: number;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @OneToMany(() => GeoNodeToLicensesDao, (geoNodeLicenses) => geoNodeLicenses.geoNode)
  geoNodeLicenses: GeoNodeToLicensesDao[];

  @OneToOne(() => RegionDao, (region) => region.geoNode)
  @JoinColumn({ name: 'region_id' })
  region: RegionDao;
}
