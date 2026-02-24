import { BaseEntity, Column, Entity, OneToOne, PrimaryGeneratedColumn } from 'typeorm';
import { GeoNodeDao } from './geo-node.dao';

@Entity('regions')
export class RegionDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'name_ru' })
  name_ru: string;

  @Column({ name: 'name_kk' })
  name_kk: string;

  @Column({ name: 'name_en' })
  name_en: string;

  @Column({ type: 'double precision' })
  latitude: number;

  @Column({ type: 'double precision' })
  longitude: number;

  @OneToOne(() => GeoNodeDao, (geoNode) => geoNode.region)
  geoNode: GeoNodeDao;
}
