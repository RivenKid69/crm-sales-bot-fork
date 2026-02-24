import { BaseEntity, Column, Entity, OneToOne, PrimaryGeneratedColumn } from 'typeorm';
import { StoreDao } from './store.dao';
import { UgdDao } from './ugd.dao';

@Entity('dgds')
export class DgdDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'name_ru' })
  name_ru: string;

  @Column({ name: 'name_kk' })
  name_kk: string;

  @Column({ name: 'name_en' })
  name_en: string;

  @OneToOne(() => StoreDao, (store) => store.dgd)
  store: StoreDao;

  @OneToOne(() => UgdDao, (ugd) => ugd.dgd)
  ugd: UgdDao;
}
