import { BaseEntity, Column, Entity, JoinColumn, OneToOne, PrimaryGeneratedColumn } from 'typeorm';
import { StoreDao } from './store.dao';
import { DgdDao } from './dgd.dao';

@Entity('ugds')
export class UgdDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'dgd_id' })
  dgd_id: number;

  @Column({ name: 'name_ru' })
  name_ru: string;

  @Column({ name: 'name_kk' })
  name_kk: string;

  @Column({ name: 'name_en' })
  name_en: string;

  @OneToOne(() => StoreDao, (store) => store.ugd)
  store: StoreDao;

  @OneToOne(() => DgdDao, (dgd) => dgd.ugd)
  @JoinColumn({ name: 'dgd_id' })
  dgd: DgdDao;
}
